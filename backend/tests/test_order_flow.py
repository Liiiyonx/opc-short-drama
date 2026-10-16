"""W7 工单闭环测试：发布 → 审核 → 投标（含能力门槛）→ 定标。

验收对应 docs/01：企业可发布工单（经审核）→ 学生可见可投标，状态机正确流转。
"""
import asyncio
import os

os.environ["LLM_PROVIDER"] = "mock"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
from app.core.config import get_settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.profile import EnterpriseProfile
from app.models.review import AbilitySnapshot
from app.models.user import User
from app.services.storage.factory import get_storage

ORDER_PAYLOAD = {
    "title": "出海短剧《都市逆袭》定制需求",
    "requirements": {"genre": "逆袭", "market": "北美", "episodes": 6, "lang": "en-US"},
    "budget_cents": 300000,
    "submit": True,
}


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
            teacher = User(username="w7teacher", password_hash=hash_password("teacher123"), role="teacher", status=1)
            enterprise = User(username="w7ent", password_hash=hash_password("ent123456"), role="enterprise", status=1)
            student = User(username="w7student", password_hash=hash_password("student123"), role="student", status=1)
            weak = User(username="w7weak", password_hash=hash_password("student123"), role="student", status=1)
            session.add_all([teacher, enterprise, student, weak])
            await session.commit()
            session.add(
                EnterpriseProfile(
                    user_id=enterprise.id,
                    company_name="测试出海传媒",
                    verify_status="approved",
                )
            )
            # student 五维 80 分；weak 五维 50 分（低于门槛）
            for dimension in ["内容创作", "跨文化沟通", "电商运营", "AI工具应用", "数据分析"]:
                session.add(AbilitySnapshot(student_id=student.id, dimension=dimension, score=80, source="review", ref_id=1))
                session.add(AbilitySnapshot(student_id=weak.id, dimension=dimension, score=50, source="review", ref_id=2))
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


def _token(client, username, password):
    resp = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["access_token"]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def test_order_full_lifecycle(client):
    teacher = _h(_token(client, "w7teacher", "teacher123"))
    ent = _h(_token(client, "w7ent", "ent123456"))
    student = _h(_token(client, "w7student", "student123"))

    # 1. 企业发布工单 → pending_review
    resp = client.post("/api/v1/orders", json=ORDER_PAYLOAD, headers=ent)
    assert resp.status_code == 200, resp.text
    order = resp.json()["data"]
    assert order["status"] == "pending_review"
    order_id = order["id"]

    # 学生此时看不到（未审核）
    resp = client.get("/api/v1/orders", headers=student)
    assert resp.json()["data"]["total"] == 0

    # 2. 教师审核通过 → published
    resp = client.post(
        f"/api/v1/orders/{order_id}/verify",
        json={"approved": True, "note": "需求清晰，通过"},
        headers=teacher,
    )
    assert resp.json()["data"]["status"] == "published"

    # 学生现在可见
    resp = client.get("/api/v1/orders", headers=student)
    assert resp.json()["data"]["total"] == 1

    # 3. 学生投标（能力 80 达标）→ bidding
    resp = client.post(
        f"/api/v1/orders/{order_id}/bid",
        json={"amount_cents": 280000, "proposal": "两周交付 6 集，含本地化"},
        headers=student,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["ability_average"] == 80.0
    bid_id = resp.json()["data"]["bid"]["id"]

    resp = client.get(f"/api/v1/orders/{order_id}", headers=ent)
    assert resp.json()["data"]["order"]["status"] == "bidding"

    # 重复投标冲突
    resp = client.post(
        f"/api/v1/orders/{order_id}/bid",
        json={"amount_cents": 270000, "proposal": "降价"},
        headers=student,
    )
    assert resp.status_code == 409

    # 4. 企业定标 → awarded
    resp = client.post(
        f"/api/v1/orders/{order_id}/award", json={"bid_id": bid_id}, headers=ent
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["order"]["status"] == "awarded"
    assert data["winning_bid"]["status"] == "won"

    # 学生查看结果：自己的投标为 won；大厅已不含该单
    resp = client.get(f"/api/v1/orders/{order_id}", headers=student)
    assert resp.json()["data"]["bids"][0]["status"] == "won"
    resp = client.get("/api/v1/orders", headers=student)
    assert resp.json()["data"]["total"] == 0


def test_order_permissions_and_threshold(client):
    teacher = _h(_token(client, "w7teacher", "teacher123"))
    ent = _h(_token(client, "w7ent", "ent123456"))
    student = _h(_token(client, "w7student", "student123"))
    weak = _h(_token(client, "w7weak", "student123"))

    resp = client.post("/api/v1/orders", json=ORDER_PAYLOAD, headers=ent)
    order_id = resp.json()["data"]["id"]

    # 学生不能审核
    resp = client.post(
        f"/api/v1/orders/{order_id}/verify", json={"approved": True}, headers=student
    )
    assert resp.status_code == 403
    # 企业不能审核自己的单
    resp = client.post(
        f"/api/v1/orders/{order_id}/verify", json={"approved": True}, headers=ent
    )
    assert resp.status_code == 403

    # 未审核不可投标
    resp = client.post(
        f"/api/v1/orders/{order_id}/bid", json={"amount_cents": 100}, headers=student
    )
    assert resp.status_code == 409

    client.post(f"/api/v1/orders/{order_id}/verify", json={"approved": True}, headers=teacher)

    # 能力不足被拒（50 < 60）
    resp = client.post(
        f"/api/v1/orders/{order_id}/bid", json={"amount_cents": 100}, headers=weak
    )
    assert resp.status_code == 403
    assert "门槛" in resp.json()["message"]

    # 未投标前企业不可定标
    resp = client.post(
        f"/api/v1/orders/{order_id}/award", json={"bid_id": 999}, headers=ent
    )
    assert resp.status_code == 409

    # 学生不能看他人投标（未投标时只能看自己的，此处为空）
    resp = client.get(f"/api/v1/orders/{order_id}", headers=student)
    assert resp.json()["data"]["bids"] == []

    # 非发布企业不可查看投标列表
    teacher_view = client.get(f"/api/v1/orders/{order_id}/bids", headers=teacher)
    assert teacher_view.status_code == 200  # 教师可见


def test_enterprise_requires_approval(client):
    """未认证企业不能发布工单（合规约束）。"""
    resp = client.post(
        "/api/v1/auth/register",
        json={"username": "w7ent2", "password": "ent123456", "role": "enterprise", "company_name": "未认证公司"},
    )
    assert resp.status_code == 200
    token = resp.json()["data"]["access_token"]
    resp = client.post("/api/v1/orders", json=ORDER_PAYLOAD, headers=_h(token))
    assert resp.status_code == 403
    assert "资质" in resp.json()["message"]
