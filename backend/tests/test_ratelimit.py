"""登录防爆破限流测试：连续失败 10 次触发 429，成功登录清零。"""
import os

os.environ["LLM_PROVIDER"] = "mock"
os.environ["TTS_PROVIDER"] = "mock"

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
from app.models.user import User


@pytest.fixture
def client(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path}/test.db", poolclass=NullPool
    )

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            session.add(
                User(
                    username="rl_user",
                    password_hash=hash_password("right-pass"),
                    role="student",
                    status=1,
                )
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


def _login(client, password):
    return client.post(
        "/api/v1/auth/login",
        json={"username": "rl_user", "password": password},
    )


def test_success_login_does_not_count(client):
    for _ in range(12):
        assert _login(client, "right-pass").status_code == 200


def test_brute_force_locks_at_10_failures(client):
    for i in range(10):
        resp = _login(client, "wrong")
        assert resp.status_code == 401
    # 第 11 次失败：429 锁定（连正确密码也不放行，防注入试探）
    resp = _login(client, "right-pass")
    assert resp.status_code == 429
    assert "临时锁定" in resp.json()["message"]
