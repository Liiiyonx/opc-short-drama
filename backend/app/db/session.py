"""异步数据库引擎与会话。

DATABASE_URL 由环境变量注入：
- 开发：sqlite+aiosqlite:///./dev.db（零配置）
- 生产：mysql+aiomysql://user:pass@host:3306/opc?charset=utf8mb4
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：请求级会话，结束时自动关闭。"""
    async with AsyncSessionLocal() as session:
        yield session
