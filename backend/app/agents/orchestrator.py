"""智能体编排器：统一处理「契约校验 → 配额检查 → 执行 → 会话/产物落库 → 调用日志」。"""
import time
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import Agent, AgentContext
from app.agents.registry import get_agent_class
from app.models.agent import AgentCallLog, AgentSession
from app.models.user import User
from app.services.llm.client import LLMError, LLMNotConfigured
from app.services.llm.quota import QuotaExceeded, ensure_quota
from app.services.llm.router import estimate_cost_cny


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def invoke_agent(
    agent_type: str,
    payload: dict,
    user: User,
    db: AsyncSession,
    work_id: int | None = None,
) -> dict:
    agent: type[Agent] = get_agent_class(agent_type)

    try:
        validated = agent.input_schema.model_validate(payload)
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

    ctx = AgentContext(db=db, user=user, work_id=work_id)
    started = time.perf_counter()
    try:
        result = await agent().run(validated, ctx)
    except LLMNotConfigured as exc:
        await _finish_failed(db, session, str(exc))
        raise HTTPException(status_code=502, detail={"code": 50002, "message": str(exc)})
    except LLMError as exc:
        await _finish_failed(db, session, str(exc))
        raise HTTPException(status_code=502, detail={"code": 50002, "message": str(exc)})
    except Exception as exc:  # 契约校验失败等未预期错误
        await _finish_failed(db, session, f"智能体执行失败：{exc}")
        raise HTTPException(
            status_code=500,
            detail={"code": 50001, "message": "智能体执行失败，请稍后重试"},
        )

    duration_ms = int((time.perf_counter() - started) * 1000)
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
            user_id=user.id,
            agent_type=agent_type,
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
    return {"session_id": session.id, "agent_type": agent_type, "result": output}


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
