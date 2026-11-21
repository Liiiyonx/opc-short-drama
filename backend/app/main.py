"""FastAPI 应用装配。

W1：健康检查 + 认证路由（auth / users）。
后续按 docs/04-API设计.md 挂载 works / pipeline / tasks / orders / ability。
启动时清扫上次进程遗留的 running 会话（worker 崩溃/重启兜底）。

健康检查三档（P0-01）：
- /livez  进程存活，永不依赖外部组件；
- /readyz DB + Redis 必须可用，否则 503（Compose 就绪探针用这个）；
- /health 全量诊断报告（worker 心跳 / 存储 / ffmpeg / AI 模式）。
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
    version="1.0.0",
    description="三端 + 一中枢 + 十智能体的 OPC 短剧出海产教融合平台",
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


@app.get("/livez", summary="存活探针：进程在即 200，不依赖任何外部组件")
async def livez() -> dict:
    return {"code": 0, "message": "alive", "data": {"status": "alive"}}


@app.get("/readyz", summary="就绪探针：DB/Redis 任一不可用即 503（编排层据此摘除实例）")
async def readyz():
    from app.core.health import readiness

    ready, detail = await readiness()
    if not ready:
        logger.warning("就绪探针失败：%s", detail)
        return JSONResponse(
            status_code=503,
            content={
                "code": 50301,
                "message": "依赖不可用，实例未就绪",
                "data": {"status": "not_ready", **detail},
            },
        )
    return {"code": 0, "message": "ready", "data": {"status": "ready", **detail}}


@app.get("/health", summary="全量诊断：DB/Redis/worker 心跳/存储/ffmpeg/AI 模式")
async def health() -> dict:
    from app.core.health import full_report

    report = await full_report()
    if report["status"] != "up":
        logger.warning("健康诊断降级：%s", {k: v for k, v in report.items() if k != "ai"})
    return {
        "code": 0,
        "message": "ok",
        "data": {"app": settings.app_name, "version": "1.0.0", **report},
    }
