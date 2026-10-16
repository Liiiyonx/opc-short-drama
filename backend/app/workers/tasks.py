"""arq worker：异步智能体任务执行。

启动（backend/ 目录）：
    python -m arq app.workers.tasks.WorkerSettings

入队由 API 侧 enqueue_agent_job 完成；任务执行后推进关联作品状态。
启动时清扫遗留 running 会话（上次 worker 崩溃/中断的兜底）。
"""
from urllib.parse import urlparse

from app.core.config import get_settings


def _redis_settings():
    from arq.connections import RedisSettings

    parsed = urlparse(get_settings().redis_url)
    return RedisSettings(
        host=parsed.hostname or "127.0.0.1",
        port=parsed.port or 6379,
        database=int(parsed.path.lstrip("/") or 0),
        password=parsed.password,
    )


_redis_settings_cached = None


async def get_redis_settings():
    global _redis_settings_cached
    if _redis_settings_cached is None:
        _redis_settings_cached = _redis_settings()
    return _redis_settings_cached


_pool = None


async def enqueue_agent_job(session_id: int) -> None:
    """API 侧调用：把会话执行任务入队。"""
    from arq import create_pool

    global _pool
    settings = await get_redis_settings()
    if _pool is None:
        _pool = await create_pool(settings)
    await _pool.enqueue_job("run_agent_job", session_id)


async def run_agent_job(ctx: dict, session_id: int) -> None:
    from sqlalchemy import select

    from app.agents.orchestrator import execute_session
    from app.db.session import AsyncSessionLocal
    from app.models.agent import AgentSession
    from app.services.works import finalize_work_from_session

    await execute_session(session_id)
    async with AsyncSessionLocal() as db:
        session = (
            await db.execute(
                select(AgentSession).where(AgentSession.id == session_id)
            )
        ).scalar_one_or_none()
        if session is not None:
            await finalize_work_from_session(db, session)


async def _sweep_on_startup(ctx: dict) -> None:
    """worker 启动清扫：把上次中断遗留的 running 会话判失败。"""
    from app.agents.orchestrator import sweep_stale_sessions
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        cleaned = await sweep_stale_sessions(db)
    if cleaned:
        print(f"[worker] 启动清扫：{cleaned} 个超时会话已判失败")


class WorkerSettings:
    functions = [run_agent_job]
    on_startup = _sweep_on_startup
    redis_settings = _redis_settings()
    max_jobs = 4
    job_timeout = 600  # 秒；视频合成留足时间
    max_tries = 2  # 瞬态故障（如 DB 抖动）允许重试一轮；execute_session 幂等（非 running 直接跳过）
