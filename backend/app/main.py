"""FastAPI 应用装配。

P0-MVP 骨架版本：仅健康检查与配置装载。
路由（auth / works / pipeline / tasks / orders / ability）在第 1-2 周按 docs/04-API设计.md 挂载。
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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


@app.get("/health")
async def health() -> dict:
    return {"code": 0, "message": "ok", "data": {"status": "up", "app": settings.app_name}}
