"""智能体 API：调用 / 会话查询（W2）。

POST /agents/{type}/invoke 的 body 为该智能体的输入契约字段
（契约见 docs/05-智能体设计.md），可附带 work_id 关联作品。
"""
from fastapi import APIRouter, Query

from app.agents.orchestrator import invoke_agent
from app.core.deps import CurrentUser, DbSession
from app.core.responses import ok
from app.models.agent import AgentSession
from app.schemas.agent import AgentSessionOut
from sqlalchemy import func, select

router = APIRouter(prefix="/agents", tags=["智能体"])


@router.post("/{agent_type}/invoke", summary="调用智能体（同步）")
async def invoke(agent_type: str, body: dict, user: CurrentUser, db: DbSession):
    work_id = body.pop("work_id", None)
    result = await invoke_agent(
        agent_type, body, user=user, db=db, work_id=work_id
    )
    return ok(result)


@router.get("/sessions", summary="我的智能体会话列表")
async def list_sessions(
    user: CurrentUser,
    db: DbSession,
    work_id: int | None = None,
    agent_type: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    stmt = select(AgentSession).where(AgentSession.user_id == user.id)
    if work_id is not None:
        stmt = stmt.where(AgentSession.work_id == work_id)
    if agent_type:
        stmt = stmt.where(AgentSession.agent_type == agent_type)
    total = (
        await db.execute(
            select(func.count()).select_from(stmt.subquery())
        )
    ).scalar_one()
    rows = (
        (
            await db.execute(
                stmt.order_by(AgentSession.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    items = [AgentSessionOut.model_validate(row).model_dump(mode="json") for row in rows]
    return ok({"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/sessions/{session_id}", summary="智能体会话详情")
async def get_session(session_id: int, user: CurrentUser, db: DbSession):
    session = (
        await db.execute(
            select(AgentSession).where(
                AgentSession.id == session_id,
                AgentSession.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if session is None:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=404, detail={"code": 40401, "message": "会话不存在"}
        )
    return ok(AgentSessionOut.model_validate(session).model_dump(mode="json"))
