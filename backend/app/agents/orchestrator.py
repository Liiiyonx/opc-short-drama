"""智能体编排器：统一处理「契约校验 → 配额检查 → 会话 → 执行 → 落库 → 调用日志」。

同步智能体：invoke_agent 直接执行并返回结果。
异步智能体（is_async=True，如 tts/compose）：创建会话 → arq 入队 →
立即返回 session_id；worker 调 execute_session 执行并落库。

兜底：sweep_stale_sessions 把超时仍 running 的会话判失败
（worker 崩溃 / 未启动场景），并联动作品状态回落，避免永久卡「生成中」。
"""
import time
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import Agent, AgentContext
from app.agents.registry import get_agent_class
from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models.agent import AgentCallLog, AgentSession
from app.models.user import User
from app.models.work import Work
from app.services.llm.client import LLMError
from app.services.llm.quota import QuotaExceeded, ensure_quota
from app.services.llm.router import estimate_cost_cny


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class QueueUnavailable(Exception):
    """任务队列（Redis）不可用。"""


async def invoke_agent(
    agent_type: str,
    payload: dict,
    user: User,
    db: AsyncSession,
    work_id: int | None = None,
) -> dict:
    agent_cls = get_agent_class(agent_type)

    try:
        validated = agent_cls.input_schema.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": 40001,
                "message": f"输入不符合 {agent_type} 智能体契约（{exc.error_count()} 处错误）",
            },
        )

    try:
        await ensure_quota(db, user.id, agent_type)
    except QuotaExceeded as exc:
        db.add(
            AgentCallLog(
                user_id=user.id,
                agent_type=agent_type,
                status="quota_exceeded",
                error=str(exc),
            )
        )
        await db.commit()
        raise HTTPException(status_code=429, detail={"code": 42901, "message": str(exc)})

    session = AgentSession(
        user_id=user.id,
        work_id=work_id,
        agent_type=agent_type,
        status="running",
        input_json=payload,
    )
    db.add(session)
    await db.flush()

    if agent_cls.is_async:
        try:
            await _enqueue_session(session.id)
        except QueueUnavailable as exc:
            await _finish_failed(db, session, f"任务队列不可用：{exc}")
            raise HTTPException(
                status_code=503,
                detail={
                    "code": 50301,
                    "message": "任务队列（Redis）不可用，请检查 REDIS_URL 与 Redis 服务",
                },
            )
        await db.commit()
        return {
            "session_id": session.id,
            "agent_type": agent_type,
            "async": True,
            "status": "running",
        }

    ctx = AgentContext(db=db, user=user, work_id=work_id, session_id=session.id)
    started = time.perf_counter()
    try:
        result = await agent_cls().run(validated, ctx)
    except LLMError as exc:
        await _finish_failed(db, session, str(exc))
        raise HTTPException(status_code=502, detail={"code": 50002, "message": str(exc)})
    except Exception as exc:
        await _finish_failed(db, session, f"智能体执行失败：{exc}")
        raise HTTPException(
            status_code=500,
            detail={"code": 50001, "message": "智能体执行失败，请稍后重试"},
        )
    await _finish_success(
        db, session, result, ctx, int((time.perf_counter() - started) * 1000)
    )
    return {
        "session_id": session.id,
        "agent_type": agent_type,
        "result": result.model_dump(mode="json"),
    }


async def execute_session(session_id: int) -> None:
    """worker 入口：加载会话 → 执行 → 落库（成功/失败均写调用日志）。"""
    async with AsyncSessionLocal() as db:
        session = (
            await db.execute(
                select(AgentSession).where(AgentSession.id == session_id)
            )
        ).scalar_one_or_none()
        if session is None or session.status != "running":
            return
        agent_cls = get_agent_class(session.agent_type)
        user = (
            await db.execute(select(User).where(User.id == session.user_id))
        ).scalar_one_or_none()
        if user is None:
            await _finish_failed(db, session, "用户不存在")
            return
        ctx = AgentContext(
            db=db, user=user, work_id=session.work_id, session_id=session.id
        )
        started = time.perf_counter()
        try:
            payload = agent_cls.input_schema.model_validate(session.input_json or {})
            result = await agent_cls().run(payload, ctx)
        except Exception as exc:
            await _finish_failed(db, session, f"智能体执行失败：{exc}")
            return
        await _finish_success(
            db, session, result, ctx, int((time.perf_counter() - started) * 1000)
        )


async def _enqueue_session(session_id: int) -> None:
    from app.workers.tasks import enqueue_agent_job

    try:
        await enqueue_agent_job(session_id)
    except Exception as exc:
        raise QueueUnavailable(str(exc))


async def _finish_success(
    db: AsyncSession,
    session: AgentSession,
    result,
    ctx: AgentContext,
    duration_ms: int,
) -> None:
    output = result.model_dump(mode="json")
    usage = ctx.usage or {}
    prompt_tokens = int(usage.get("prompt_tokens", 0))
    completion_tokens = int(usage.get("completion_tokens", 0))
    session.status = "success"
    session.output_json = output
    session.finished_at = _now()
    db.add(
        AgentCallLog(
            session_id=session.id,
            user_id=session.user_id,
            agent_type=session.agent_type,
            provider=usage.get("provider", ""),
            model=usage.get("model", ""),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            duration_ms=duration_ms,
            cost_est=estimate_cost_cny(
                usage.get("model", ""), prompt_tokens, completion_tokens
            ),
            status="success",
        )
    )
    await db.commit()


async def _finish_failed(db: AsyncSession, session: AgentSession, error: str) -> None:
    session.status = "failed"
    session.error = error[:2000]
    session.finished_at = _now()
    db.add(
        AgentCallLog(
            session_id=session.id,
            user_id=session.user_id,
            agent_type=session.agent_type,
            status="failed",
            error=error[:2000],
        )
    )
    await db.commit()


# ---------- 卡死任务兜底 ----------


def _stale_cutoff(seconds: int) -> datetime:
    return _now() - timedelta(seconds=seconds)


async def sweep_stale_sessions(
    db: AsyncSession, session_id: int | None = None
) -> int:
    """把超时仍处于 running 的会话判定为失败，并联动作品状态。

    - session_id 为 None：全量清扫（进程启动 / worker 启动时调用）；
    - session_id 指定：只检查该会话（前端轮询时的惰性兜底）。
    返回处理条数。
    """
    settings = get_settings()
    timeout = max(60, settings.agent_task_timeout_seconds)
    message = (
        f"任务超时：已等待超过 {timeout // 60} 分钟仍未完成"
        "（worker 可能未启动或已中断），请确认后台 worker 运行后重试"
    )
    stmt = select(AgentSession).where(
        AgentSession.status == "running",
        AgentSession.created_at < _stale_cutoff(timeout),
    )
    if session_id is not None:
        stmt = stmt.where(AgentSession.id == session_id)
    sessions = list((await db.execute(stmt)).scalars().all())
    if not sessions:
        return 0

    work_ids = [s.work_id for s in sessions if s.work_id]
    works: dict[int, Work] = {}
    if work_ids:
        rows = (
            await db.execute(select(Work).where(Work.id.in_(work_ids)))
        ).scalars().all()
        works = {w.id: w for w in rows}

    for session in sessions:
        session.status = "failed"
        session.error = message
        session.finished_at = _now()
        db.add(
            AgentCallLog(
                session_id=session.id,
                user_id=session.user_id,
                agent_type=session.agent_type,
                status="timeout",
                error=message,
            )
        )
        work = works.get(session.work_id) if session.work_id else None
        if work is not None and work.status == "generating":
            work.status = "failed"
    await db.commit()
    return len(sessions)
