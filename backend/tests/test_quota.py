"""配额逻辑测试：mock 测试桩不占用户配额（2026-10-16 修复）。"""
import os

os.environ["LLM_PROVIDER"] = "mock"
os.environ["TTS_PROVIDER"] = "mock"

from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
from app.core.config import get_settings
from app.core.security import hash_password
from app.db.base import Base
from app.models.agent import AgentCallLog
from app.models.user import User
from app.services.llm.quota import (
    MEDIA_AGENTS,
    TEXT_AGENTS,
    QuotaExceeded,
    count_today_calls,
    ensure_quota,
)


@pytest.fixture
async def db(tmp_path, monkeypatch):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path}/test.db", poolclass=NullPool
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path / "storage"))
    monkeypatch.setenv("QUOTA_MEDIA_CALLS_PER_USER_DAY", "2")
    get_settings.cache_clear()
    async with factory() as session:
        user = User(
            username="quota_user",
            password_hash=hash_password("test123456"),
            role="student",
            status=1,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        yield session, user
    get_settings.cache_clear()
    await engine.dispose()


def _log(session, user, agent_type, provider):
    row = AgentCallLog(
        user_id=user.id,
        agent_type=agent_type,
        provider=provider,
        status="success",
        created_at=datetime.now(),
    )
    session.add(row)
    return row


async def test_mock_calls_do_not_consume_quota(db):
    session, user = db
    for _ in range(5):
        _log(session, user, "tts", "mock")
    await session.commit()
    assert await count_today_calls(session, user.id, MEDIA_AGENTS) == 0
    # 配额未耗尽 → 仍可调用
    await ensure_quota(session, user.id, "tts")


async def test_real_calls_consume_quota_and_block_at_limit(db):
    session, user = db
    _log(session, user, "tts", "edge-tts")
    _log(session, user, "compose", "ffmpeg")
    await session.commit()
    assert await count_today_calls(session, user.id, MEDIA_AGENTS) == 2
    with pytest.raises(QuotaExceeded):
        await ensure_quota(session, user.id, "tts")

    # 文本类独立计数
    assert await count_today_calls(session, user.id, TEXT_AGENTS) == 0