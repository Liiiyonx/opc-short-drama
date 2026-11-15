"""FastAPI 应用装配。

W1：健康检查 + 认证路由（auth / users）。
后续按 docs/04-API设计.md 挂载 works / pipeline / tasks / orders / ability。
启动时清扫上次进程遗留的 running 会话（worker 崩溃/重启兜底）。
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import (
    ability,
    agent_tasks,
    agents,
    analytics,
    auth,
    courses,
    files,
    orders,
    portfolio,
    tasks,
    users,
    works,
)
from app.core.config import get_settings
from app.core.middleware import AccessLogMiddleware

logger = logging.getLogger("opc.main")

settings = get_settings()

# CORS 策略：显式配置优先；prod 未配置 = 同源部署不开放跨域；dev 放开（vite 5173 → 8000）
if settings.cors_origins.strip():
    cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
elif settings.opc_env == "prod":
    cors_origins = []
else:
    cors_origins = ["*"]


@asynccontextmanager
async def lifespan(_: FastAPI):
    # 启动清扫：把上次进程退出时遗留的 running 会话判失败并回落作品状态。
    # 失败不阻塞启动（如 DB 未迁移）。
    try:
        from app.agents.orchestrator import sweep_stale_sessions
        from app.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            cleaned = await sweep_stale_sessions(db)
            if cleaned:
                logger.warning("启动清扫：%d 个超时会话已判失败", cleaned)
    except Exception as exc:  # noqa: BLE001
        logger.warning("启动清扫跳过：%s", exc)
    yield
    # 优雅关闭：释放 LLM 网关复用的 HTTP 连接池
    try:
        from app.services.llm.client import close_clients

        await close_clients()
    except Exception:  # noqa: BLE001
        pass


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="三端 + 一中枢 + 八智能体的 OPC 短剧出海产教融合平台（P0-MVP）",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
# 纯 ASGI 访问日志 + X-Request-ID（add_middleware 包一层，仍是 ASGI 直通）
app.add_middleware(AccessLogMiddleware)


@app.exception_handler(HTTPException)
async def unified_http_exception_handler(request, exc: HTTPException):
    """HTTPException 统一转成 {code, message, data} 包裹。"""
    detail = exc.detail if isinstance(exc.detail, dict) else {
        "code": exc.status_code,
        "message": str(exc.detail),
    }
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": detail.get("code", exc.status_code),
            "message": detail.get("message", "error"),
            "data": None,
        },
    )


app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(agents.router, prefix="/api/v1")
app.include_router(works.router, prefix="/api/v1")
app.include_router(files.router, prefix="/api/v1")
app.include_router(agent_tasks.router, prefix="/api/v1")
app.include_router(tasks.router, prefix="/api/v1")
app.include_router(ability.router, prefix="/api/v1")
app.include_router(courses.router, prefix="/api/v1")
app.include_router(orders.router, prefix="/api/v1")
app.include_router(analytics.router, prefix="/api/v1")
app.include_router(portfolio.router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict:
    """深度健康检查：DB / Redis 连通性（降级仍返回 200，便于编排层不抖动）。"""
    import asyncio

    from sqlalchemy import text

    db_status, redis_status = "up", "up"
    try:
        from app.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            await asyncio.wait_for(db.execute(text("SELECT 1")), timeout=2)
    except Exception:  # noqa: BLE001
        db_status = "down"
    try:
        from urllib.parse import urlparse

        import redis.asyncio as aioredis

        parsed = urlparse(settings.redis_url)
        r = aioredis.from_url(
            settings.redis_url,
            socket_connect_timeout=2,
            socket_timeout=2,
            password=parsed.password,
        )
        try:
            await asyncio.wait_for(r.ping(), timeout=2)
        finally:
            await r.aclose()
    except Exception:  # noqa: BLE001
        redis_status = "down"

    status = "up" if db_status == "up" and redis_status == "up" else "degraded"
    if status != "up":
        logger.warning("健康检查降级：db=%s redis=%s", db_status, redis_status)
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "status": status,
            "db": db_status,
            "redis": redis_status,
            "app": settings.app_name,
        },
    }
