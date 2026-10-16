"""W2 智能体链路测试。

用 LLM_PROVIDER=mock 测试桩跑完整链路（校验→配额→会话→日志→成本），
无需真实密钥；另覆盖未知类型、配额超限、无密钥明确报错三条边界。

运行：cd backend && python -m pytest tests/ -v
"""
import os

# 必须在导入 app.* 之前设置：mock 是显式测试桩，不是回退路径
os.environ["LLM_PROVIDER"] = "mock"

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401  注册全部模型
from app.agents.orchestrator import invoke_agent
from app.core.config import get_settings
from app.core.security import hash_password
from app.db.base import Base
from app.models.agent import AgentCallLog, AgentSession
from app.models.user import User

SCRIPT_PAYLOAD = {
    "genre": "逆袭",
    "target_market": "北美",
    "episodes": 2,
    "episode_minutes": 2,
    "keywords": ["外卖", "暗号"],
}


@pytest.fixture
async def db(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        user = User(
            username="tester",
            password_hash=hash_password("test123456"),
            role="student",
            status=1,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        yield session
    await engine.dispose()


@pytest.fixture
def reset_settings(monkeypatch):
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_script_agent_full_chain(db):
    user = (await db.execute(select(User).where(User.username == "tester"))).scalar_one()
    result = await invoke_agent("script", dict(SCRIPT_PAYLOAD), user=user, db=db)

    assert result["agent_type"] == "script"
    outline = result["result"]
    assert outline["title"] and len(outline["episodes"]) == 2
    assert outline["episodes"][0]["scenes"][0]["dialogue"]

    session = (
        await db.execute(
            select(AgentSession).where(AgentSession.id == result["session_id"])
        )
    ).scalar_one()
    assert session.status == "success"
    assert session.output_json["title"] == outline["title"]

    log = (
        await db.execute(
            select(AgentCallLog).where(AgentCallLog.session_id == session.id)
        )
    ).scalar_one()
    assert log.status == "success"
    assert log.provider == "mock"
    assert log.prompt_tokens == 128 and log.completion_tokens == 396
    assert float(log.cost_est) > 0  # deepseek-chat 价格表可估算


async def test_quota_exceeded(db, monkeypatch, reset_settings):
    monkeypatch.setenv("QUOTA_TEXT_CALLS_PER_USER_DAY", "1")
    get_settings.cache_clear()
    user = (await db.execute(select(User).where(User.username == "tester"))).scalar_one()

    await invoke_agent("script", dict(SCRIPT_PAYLOAD), user=user, db=db)
    with pytest.raises(HTTPException) as exc_info:
        await invoke_agent("script", dict(SCRIPT_PAYLOAD), user=user, db=db)
    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["code"] == 42901


async def test_unknown_agent_type(db):
    user = (await db.execute(select(User).where(User.username == "tester"))).scalar_one()
    with pytest.raises(HTTPException) as exc_info:
        await invoke_agent("no_such_agent", {}, user=user, db=db)
    assert exc_info.value.status_code == 404


async def test_invalid_payload(db):
    user = (await db.execute(select(User).where(User.username == "tester"))).scalar_one()
    with pytest.raises(HTTPException) as exc_info:
        await invoke_agent("script", {"genre": "逆袭"}, user=user, db=db)  # 缺 target_market
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == 40001


async def test_no_api_key_clear_error(db, monkeypatch, reset_settings):
    """无密钥且非 mock：必须明确报错并引导去 secrets 文件，不静默回退。"""
    monkeypatch.setenv("LLM_PROVIDER", "openai_compat")
    monkeypatch.setenv("LLM_API_KEY", "")
    get_settings.cache_clear()
    user = (await db.execute(select(User).where(User.username == "tester"))).scalar_one()
    with pytest.raises(HTTPException) as exc_info:
        await invoke_agent("script", dict(SCRIPT_PAYLOAD), user=user, db=db)
    assert exc_info.value.status_code == 502
    assert "opc_secrets.env" in exc_info.value.detail["message"]

    session = (
        await db.execute(select(AgentSession).order_by(AgentSession.id.desc()))
    ).scalars().first()
    assert session.status == "failed"
    assert "LLM_API_KEY" in (session.error or "")
