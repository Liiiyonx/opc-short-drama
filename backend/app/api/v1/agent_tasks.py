"""异步任务进度查询：GET /api/v1/agent-tasks/{task_id}。

（与教学任务 /tasks 区分命名；task_id 即 agent_sessions.id）
前端轮询 status：running → success / failed，成功后带 result。

兜底：查询时对「超时仍 running」的会话做惰性清扫（worker 未运行 /
已崩溃场景），把它判为 failed 并带出可读的错误信息与 work_id，
前端可据此刷新作品状态、给出明确提示。
"""
from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.agents.orchestrator import sweep_stale_sessions
from app.core.deps import CurrentUser, DbSession
from app.core.responses import ok
from app.models.agent import AgentSession

router = APIRouter(prefix="/agent-tasks", tags=["异步任务"])


@router.get("/{task_id}", summary="异步智能体任务进度查询")
async def get_agent_task(task_id: int, user: CurrentUser, db: DbSession):
    session = (
        await db.execute(
            select(AgentSession).where(
                AgentSession.id == task_id,
                AgentSession.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if session is None and user.role == "admin":
        session = (
            await db.execute(
                select(AgentSession).where(AgentSession.id == task_id)
            )
        ).scalar_one_or_none()
    if session is None:
        raise HTTPException(
            status_code=404, detail={"code": 40401, "message": "任务不存在"}
        )
    # 惰性兜底：本会话若已超时仍 running → 判失败（含作品回落）
    if session.status == "running":
        cleaned = await sweep_stale_sessions(db, session_id=session.id)
        if cleaned:
            await db.refresh(session)
    return ok(
        {
            "task_id": session.id,
            "agent_type": session.agent_type,
            "work_id": session.work_id,
            "status": session.status,
            "result": session.output_json if session.status == "success" else None,
            "error": session.error if session.status == "failed" else None,
        }
    )
