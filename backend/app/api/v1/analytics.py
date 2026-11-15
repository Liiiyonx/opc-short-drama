"""用量分析（教师/管理员）：agent_call_logs 聚合（Langfuse 式成本可观测）。

GET /api/v1/analytics/usage?days=14
返回：总调用/总 tokens/总成本、按智能体分布、按日趋势、用户 Top5。
数据源即既有调用日志，零新表。
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.core.deps import CurrentUser, DbSession, require_role
from app.core.responses import ok
from app.models.agent import AgentCallLog
from app.models.user import User

router = APIRouter(prefix="/analytics", tags=["分析"])

_WINDOW_DAYS = 14


def _success_where(days: int):
    since = datetime.now() - timedelta(days=days)
    return AgentCallLog.created_at >= since, AgentCallLog.status == "success"


@router.get(
    "/usage",
    summary="AI 用量聚合（tokens/成本/分布）",
    dependencies=[Depends(require_role("teacher", "admin"))],
)
async def usage_stats(
    user: CurrentUser,
    db: DbSession,
    days: int = Query(default=_WINDOW_DAYS, ge=1, le=90),
):
    cond_time, cond_status = _success_where(days)
    where = (cond_time, cond_status)

    # 总量
    total_row = (
        await db.execute(
            select(
                func.count(),
                func.coalesce(func.sum(AgentCallLog.prompt_tokens + AgentCallLog.completion_tokens), 0),
                func.coalesce(func.sum(AgentCallLog.cost_est), 0),
            ).where(*where)
        )
    ).one()
    total = {
        "calls": int(total_row[0]),
        "tokens": int(total_row[1]),
        "cost": round(float(total_row[2]), 4),
    }

    # 按智能体分布
    agent_rows = (
        await db.execute(
            select(
                AgentCallLog.agent_type,
                func.count(),
                func.coalesce(func.sum(AgentCallLog.prompt_tokens + AgentCallLog.completion_tokens), 0),
                func.coalesce(func.sum(AgentCallLog.cost_est), 0),
            )
            .where(*where)
            .group_by(AgentCallLog.agent_type)
            .order_by(func.count().desc())
        )
    ).all()
    by_agent = [
        {
            "agent_type": row[0],
            "calls": int(row[1]),
            "tokens": int(row[2]),
            "cost": round(float(row[3]), 4),
        }
        for row in agent_rows
    ]

    # 按日趋势（DATE() 对 SQLite/MySQL 均适用）
    day_rows = (
        await db.execute(
            select(
                func.date(AgentCallLog.created_at),
                func.count(),
                func.coalesce(func.sum(AgentCallLog.prompt_tokens + AgentCallLog.completion_tokens), 0),
                func.coalesce(func.sum(AgentCallLog.cost_est), 0),
            )
            .where(*where)
            .group_by(func.date(AgentCallLog.created_at))
            .order_by(func.date(AgentCallLog.created_at))
        )
    ).all()
    by_day = [
        {
            "date": str(row[0]),
            "calls": int(row[1]),
            "tokens": int(row[2]),
            "cost": round(float(row[3]), 4),
        }
        for row in day_rows
    ]

    # 用户 Top5（按成本）
    user_rows = (
        await db.execute(
            select(
                User.username,
                func.count(),
                func.coalesce(func.sum(AgentCallLog.prompt_tokens + AgentCallLog.completion_tokens), 0),
                func.coalesce(func.sum(AgentCallLog.cost_est), 0),
            )
            .join(User, User.id == AgentCallLog.user_id)
            .where(*where)
            .group_by(User.username)
            .order_by(func.sum(AgentCallLog.cost_est).desc())
            .limit(5)
        )
    ).all()
    top_users = [
        {
            "username": row[0],
            "calls": int(row[1]),
            "tokens": int(row[2]),
            "cost": round(float(row[3]), 4),
        }
        for row in user_rows
    ]

    return ok({"days": days, "total": total, "by_agent": by_agent, "by_day": by_day, "top_users": top_users})
