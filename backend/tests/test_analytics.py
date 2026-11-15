"""用量分析端点测试：教师可见、学生 403、聚合数值正确。"""
import os

os.environ["LLM_PROVIDER"] = "mock"
os.environ["TTS_PROVIDER"] = "mock"

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
from app.core.config import get_settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.agent import AgentCallLog
from app.models.user import User


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path}/test.db", poolclass=NullPool
    )

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            session.add_all(
                [
                    User(username="t1", password_hash=hash_password("p123456"), role="teacher", status=1),
                    User(username="s1", password_hash=hash_password("p123456"), role="student", status=1),
                ]
            )
            await session.commit()
            users = (
                (await session.execute(select(User))).scalars().all()
            )
            uid = {u.username: u.id for u in users}
            session.add_all(
                [
                    AgentCallLog(user_id=uid["s1"], agent_type="script", provider="openai_compat",
                                 model="m", prompt_tokens=100, completion_tokens=50,
                                 cost_est=0.01, status="success", created_at=datetime.now()),
                    AgentCallLog(user_id=uid["s1"], agent_type="script", provider="openai_compat",
                                 model="m", prompt_tokens=200, completion_tokens=100,
                                 cost_est=0.02, status="success", created_at=datetime.now()),
                    # 失败调用不计量
                    AgentCallLog(user_id=uid["s1"], agent_type="tts", provider="edge",
                                 model="", cost_est=0, status="failed", created_at=datetime.now()),
                ]
            )
            await session.commit()
        return factory

    factory = __import__("asyncio").run(setup())

    async def override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    get_settings.cache_clear()

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
    get_settings.cache_clear()


from sqlalchemy import select  # noqa: E402


def _login(client, username):
    resp = client.post("/api/v1/auth/login", json={"username": username, "password": "p123456"})
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


def test_usage_requires_teacher(client):
    r = client.get("/api/v1/analytics/usage", headers=_login(client, "s1"))
    assert r.status_code == 403


def test_usage_aggregation(client):
    r = client.get("/api/v1/analytics/usage?days=14", headers=_login(client, "t1"))
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total"]["calls"] == 2
    assert data["total"]["tokens"] == 100 + 50 + 200 + 100
    assert abs(data["total"]["cost"] - 0.03) < 1e-6
    assert data["by_agent"][0]["agent_type"] == "script"
    assert len(data["by_day"]) >= 1
    assert data["top_users"][0]["username"] == "s1"
