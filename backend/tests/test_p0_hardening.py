"""P0 加固回归：三档健康检查 / 注册角色红线 / token 刷新闭环。

对应 docs/08-三创赛优化计划书.md P0-01 / P0-02 / P0-03（后端部分）。
"""
import asyncio
import os

os.environ["LLM_PROVIDER"] = "mock"

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
from app.services.storage.factory import get_storage


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
            session.add(
                User(
                    username="p0student",
                    password_hash=hash_password("student123"),
                    role="student",
                    status=1,
                )
            )
            await session.commit()
        return factory

    session_factory = asyncio.run(setup())

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path / "storage"))
    get_settings.cache_clear()
    get_storage.cache_clear()

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    get_settings.cache_clear()
    get_storage.cache_clear()


def _h(token):
    return {"Authorization": f"Bearer {token}"}


# ---------- P0-01 健康检查三档 ----------


def test_livez_always_alive(client):
    resp = client.get("/livez")
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "alive"


def test_readyz_ok_when_dependencies_up(client):
    resp = client.get("/readyz")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["db"] == "up"
    assert data["redis"] == "up"


def test_health_full_report(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()["data"]
    # 全量诊断字段齐全：编排层与演示闸门依赖这些键
    for key in ("status", "db", "redis", "worker", "storage", "ffmpeg", "ai"):
        assert key in data, f"缺少 {key}"
    assert data["db"] == "up"
    assert data["storage"] == "up"
    assert set(data["ai"].keys()) == {"llm_provider", "llm_model", "tts_provider"}


def test_readyz_503_when_db_down(client, monkeypatch):
    """DB 故障时 /readyz 必须 503（Compose 不能把故障实例判为健康）。"""

    class BrokenSession:
        # 探针用法：async with AsyncSessionLocal() as db: await db.execute(...)
        async def __aenter__(self):
            raise RuntimeError("simulated db outage")

        async def __aexit__(self, *args):
            return False

    # AsyncSessionLocal 在模块导入时已绑定引擎，改 env 无效；直接替换工厂
    monkeypatch.setattr("app.db.session.AsyncSessionLocal", BrokenSession)
    with TestClient(app) as c:
        resp = c.get("/readyz")
    assert resp.status_code == 503
    assert resp.json()["data"]["db"] == "down"


def test_readyz_503_when_redis_down(client, monkeypatch):
    """Redis 故障时 /readyz 必须 503（探针超时 2s ≤ 3s 验收线）。

    用指向不存在端口的 REDIS_URL 模拟连接拒绝（探针每次新建连接，无缓存）。
    """
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/1")  # 端口 1 必然拒绝连接
    get_settings.cache_clear()
    with TestClient(app) as c:
        resp = c.get("/readyz")
    assert resp.status_code == 503
    assert resp.json()["data"]["redis"] == "down"
    get_settings.cache_clear()


# ---------- P0-02 注册角色红线 ----------


def test_register_student_allowed(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={"username": "p0newstu", "password": "student123", "role": "student", "major": "电子商务"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["user"]["role"] == "student"


def test_register_teacher_enterprise_rejected(client):
    for role, payload in (
        ("teacher", {"username": "p0badtea", "password": "teacher123", "role": "teacher"}),
        ("enterprise", {"username": "p0badent", "password": "ent123456", "role": "enterprise", "company_name": "X"}),
    ):
        resp = client.post("/api/v1/auth/register", json=payload)
        assert resp.status_code == 403, f"{role} 不应允许自助注册"
        assert resp.json()["code"] == 40301


# ---------- P0-03 refresh token 闭环（后端侧） ----------


def test_refresh_token_roundtrip(client):
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "p0student", "password": "student123"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data.get("refresh_token"), "登录必须下发 refresh token"

    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": data["refresh_token"]})
    assert resp.status_code == 200
    assert resp.json()["data"]["access_token"]

    # refresh token 不能当 access token 用（类型校验）
    resp = client.get("/api/v1/users/me", headers=_h(data["refresh_token"]))
    assert resp.status_code == 401

    # 用 access token 冒充 refresh token 应被拒
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": data["access_token"]})
    assert resp.status_code == 401
