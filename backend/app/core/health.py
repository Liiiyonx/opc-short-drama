"""健康探针：DB / Redis / worker 心跳 / 存储 / ffmpeg / AI 模式。

三档健康端点共用：
- /livez  仅进程存活（永不依赖外部组件）；
- /readyz DB + Redis 必须可用，否则 503（编排层据此判实例不就绪）；
- /health 全量诊断报告（含 worker 心跳、存储、ffmpeg、AI 模式），始终 200。

worker 心跳：arq worker 每 15s 写 `worker:heartbeat`（TTL 40s）；
心跳缺失 = worker 进程死亡或队列断连，业务探针即失败。
"""
import asyncio
import shutil
import socket
import time
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import text

WORKER_HEARTBEAT_KEY = "worker:heartbeat"
# TTL 25s：worker 每 15s 续期，被杀后最坏 25s 检出（≤30s 验收线），且容忍 1 次漏跳
WORKER_HEARTBEAT_TTL = 25

_PROBE_TIMEOUT = 2.0


async def probe_db() -> str:
    try:
        from app.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            await asyncio.wait_for(db.execute(text("SELECT 1")), timeout=_PROBE_TIMEOUT)
        return "up"
    except Exception:  # noqa: BLE001
        return "down"


async def probe_redis() -> str:
    try:
        import redis.asyncio as aioredis

        settings = _settings()
        parsed = urlparse(settings.redis_url)
        r = aioredis.from_url(
            settings.redis_url,
            socket_connect_timeout=_PROBE_TIMEOUT,
            socket_timeout=_PROBE_TIMEOUT,
            password=parsed.password,
        )
        try:
            await asyncio.wait_for(r.ping(), timeout=_PROBE_TIMEOUT)
        finally:
            await r.aclose()
        return "up"
    except Exception:  # noqa: BLE001
        return "down"


async def probe_worker() -> str:
    """worker 心跳：Redis 心跳键在 TTL 内 = up。"""
    try:
        import redis.asyncio as aioredis

        settings = _settings()
        parsed = urlparse(settings.redis_url)
        r = aioredis.from_url(
            settings.redis_url,
            socket_connect_timeout=_PROBE_TIMEOUT,
            socket_timeout=_PROBE_TIMEOUT,
            password=parsed.password,
        )
        try:
            await asyncio.wait_for(r.exists(WORKER_HEARTBEAT_KEY), timeout=_PROBE_TIMEOUT)
            ttl = await r.ttl(WORKER_HEARTBEAT_KEY)
        finally:
            await r.aclose()
        return "up" if ttl and ttl > 0 else "down"
    except Exception:  # noqa: BLE001
        return "down"


def probe_storage() -> str:
    """存储面探针：local 检查目录可写；minio 检查 TCP 可达。"""
    settings = _settings()
    try:
        if settings.storage_backend == "minio":
            host, _, port = settings.minio_endpoint.partition(":")
            port = int(port or 9000)
            with socket.create_connection((host, port), timeout=_PROBE_TIMEOUT):
                pass
            return "up"
        base = Path(settings.local_storage_path)
        base.mkdir(parents=True, exist_ok=True)
        probe = base / "_health_probe"
        probe.write_text(str(int(time.time())), encoding="utf-8")
        probe.unlink(missing_ok=True)
        return "up"
    except Exception:  # noqa: BLE001
        return "down"


def probe_ffmpeg() -> str:
    return "up" if shutil.which(_settings().ffmpeg_path) else "down"


def ai_mode() -> dict:
    settings = _settings()
    return {
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model_default if settings.llm_provider != "mock" else "mock",
        "tts_provider": settings.tts_provider,
    }


async def readiness() -> tuple[bool, dict]:
    """/readyz 判定：DB + Redis 必须 up。"""
    db_status, redis_status = await asyncio.gather(probe_db(), probe_redis())
    detail = {"db": db_status, "redis": redis_status}
    return db_status == "up" and redis_status == "up", detail


async def full_report() -> dict:
    """/health 全量诊断（诊断端点始终返回 200，由 data.status 表达健康度）。"""
    db_status, redis_status, worker_status = await asyncio.gather(
        probe_db(), probe_redis(), probe_worker()
    )
    report = {
        "status": "up",
        "db": db_status,
        "redis": redis_status,
        "worker": worker_status,
        "storage": probe_storage(),
        "ffmpeg": probe_ffmpeg(),
        "ai": ai_mode(),
        "checked_at": int(time.time()),
    }
    critical_down = db_status != "up" or redis_status != "up"
    # worker 失联只降级不置 down：API 本身仍可服务同步智能体
    if critical_down:
        report["status"] = "down"
    elif worker_status != "up":
        report["status"] = "degraded"
    return report


def _settings():
    from app.core.config import get_settings

    return get_settings()
