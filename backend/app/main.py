"""FastAPI 应用装配。

W1：健康检查 + 认证路由（auth / users）。
后续按 docs/04-API设计.md 挂载 works / pipeline / tasks / orders / ability。
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import (
    ability,
    agent_tasks,
    agents,
    auth,
    courses,
    files,
    tasks,
    users,
    works,
)
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="三端 + 一中枢 + 八智能体的 OPC 短剧出海产教融合平台（P0-MVP）",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # P0 开发期放开；生产收敛到三端子域名
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.get("/health")
async def health() -> dict:
    return {"code": 0, "message": "ok", "data": {"status": "up", "app": settings.app_name}}
