"""智能体配额：每用户每日按类别限次。

超限抛 QuotaExceeded（上层转 42901），并落 status=quota_exceeded 的调用日志。
"""
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.agent import AgentCallLog

TEXT_AGENTS = {"script", "storyboard", "translate", "analyze", "optimize", "match"}
MEDIA_AGENTS = {"tts", "publish"}


class QuotaExceeded(Exception):
    """今日配额已用完。"""


def _today_start() -> datetime:
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)


async def count_today_calls(db: AsyncSession, user_id: int, agent_types: set[str]) -> int:
    if not agent_types:
        return 0
    result = await db.execute(
        select(func.count())
        .select_from(AgentCallLog)
        .where(
            AgentCallLog.user_id == user_id,
            AgentCallLog.created_at >= _today_start(),
            AgentCallLog.agent_type.in_(sorted(agent_types)),
        )
    )
    return int(result.scalar_one())


async def ensure_quota(db: AsyncSession, user_id: int, agent_type: str) -> None:
    settings = get_settings()
    if agent_type in TEXT_AGENTS:
        limit = settings.quota_text_calls_per_user_day
        category = TEXT_AGENTS
    else:
        limit = settings.quota_media_calls_per_user_day
        category = MEDIA_AGENTS
    used = await count_today_calls(db, user_id, category)
    if used >= limit:
        raise QuotaExceeded(
            f"今日{agent_type}类智能体配额已用完（{used}/{limit}），请明日再试或联系教师调整"
        )
