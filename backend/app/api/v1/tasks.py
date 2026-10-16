"""异步任务进度查询：GET /api/v1/tasks/{task_id}。

task_id 即 agent_sessions.id；前端轮询 status：
running → success / failed，成功后带 result。
"""
from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession
from app.core.responses import ok
from app.models.agent import AgentSession

router = APIRouter(prefix="/tasks", tags=["任务"])


@router.get("/{task_id}", summary="异步任务进度查询")
async def get_task(task_id: int, user: CurrentUser, db: DbSession):
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
    return ok(
        {
            "task_id": session.id,
            "agent_type": session.agent_type,
            "status": session.status,
            "result": session.output_json if session.status == "success" else None,
            "error": session.error if session.status == "failed" else None,
        }
    )
