"""W6 教学闭环测试：发布任务 → 学生提交 → 教师 Rubric 批改 → 能力快照。

验收对应 docs/01：教师可发布任务 → 学生提交 → 教师批改 → 五维能力分变化。
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
from app.models.user import User
from app.models.work import Work
from app.services.storage.factory import get_storage

TASK_PAYLOAD = {
    "title": "短剧出海实训任务一",
    "brief": "产出一部 2 集短剧的完整成片",
    "team_rule": "free",
    "publish": True,
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
            session.add_all(
                [
                    User(username="w6teacher", password_hash=hash_password("teacher123"), role="teacher", status=1),
                    User(username="w6teacher2", password_hash=hash_password("teacher123"), role="teacher", status=1),
                    User(username="w6student", password_hash=hash_password("student123"), role="student", status=1),
                ]
            )
            await session.commit()
            student = (
                await session.execute(
                    select(User).where(User.username == "w6student")
                )
            ).scalar_one()
            work = Work(
                title="我的短剧成片",
                type="video",
                owner_type="user",
                owner_id=student.id,
                created_by=student.id,
                status="ready",
                version=1,
                ai_declare_json={"agents_used": ["script", "tts"], "human_edit_ratio": 0.35},
            )
            session.add(work)
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


def _token(client: TestClient, username: str, password: str) -> str:
    resp = client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["access_token"]


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_full_teaching_flow(client):
    teacher = _h(_token(client, "w6teacher", "teacher123"))
    student = _h(_token(client, "w6student", "student123"))

    # 1. 教师发布任务
    resp = client.post("/api/v1/tasks", json=TASK_PAYLOAD, headers=teacher)
    assert resp.status_code == 200, resp.text
    task = resp.json()["data"]
    assert task["status"] == "published"
    assert len(task["rubric_json"]["criteria"]) == 5
    task_id = task["id"]

    # 2. 学生可见任务并提交作品
    resp = client.get("/api/v1/tasks", headers=student)
    assert resp.json()["data"]["total"] == 1
    resp = client.post(
        f"/api/v1/tasks/{task_id}/submit",
        json={"work_ids": [1], "note": "第一版成片，请老师指正"},
        headers=student,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "submitted"

    # 3. 教师查看提交列表
    resp = client.get(f"/api/v1/tasks/{task_id}/submissions", headers=teacher)
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["submitter_name"] == "w6student"
    assert items[0]["works"][0]["title"] == "我的短剧成片"

    # 4. 教师 Rubric 批改（按默认五项打分）
    scores = [
        {"key": "content_creation", "score": 88},
        {"key": "cross_culture", "score": 76},
        {"key": "ecommerce", "score": 70},
        {"key": "ai_tools", "score": 92},
        {"key": "analytics", "score": 65},
    ]
    resp = client.post(
        f"/api/v1/works/1/review",
        json={"criterion_scores": scores, "comment": "内容扎实，数据复盘需加强"},
        headers=teacher,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    expected_total = round(
        88 * 0.25 + 76 * 0.20 + 70 * 0.20 + 92 * 0.20 + 65 * 0.15, 2
    )
    assert data["total"] == expected_total
    assert data["passed"] is True
    assert float(data["review"]["ai_diff_ratio"]) == 0.35  # 来自 AI 声明的人工修改比例

    # 5. 学生查看批改结果
    resp = client.get("/api/v1/works/1/review", headers=student)
    latest = resp.json()["data"]["latest"]
    assert latest["comment"] == "内容扎实，数据复盘需加强"
    assert latest["rubric_score_json"]["items"]["ai_tools"]["score"] == 92

    # 6. 学生五维能力快照已更新
    resp = client.get("/api/v1/ability/students/3", headers=student)
    ability = resp.json()["data"]
    assert ability["latest"]["内容创作"] == 88
    assert ability["latest"]["跨文化沟通"] == 76
    assert ability["latest"]["AI工具应用"] == 92
    assert ability["review_count"] == 1
    assert len(ability["history"]) == 5

    # 7. 提交状态推进为 reviewed
    resp = client.get(f"/api/v1/tasks/{task_id}/submissions", headers=teacher)
    assert resp.json()["data"]["items"][0]["status"] == "reviewed"


def test_review_permissions(client):
    teacher = _h(_token(client, "w6teacher", "teacher123"))
    teacher2 = _h(_token(client, "w6teacher2", "teacher123"))
    student = _h(_token(client, "w6student", "student123"))

    resp = client.post("/api/v1/tasks", json=TASK_PAYLOAD, headers=teacher)
    task_id = resp.json()["data"]["id"]
    client.post(
        f"/api/v1/tasks/{task_id}/submit",
        json={"work_ids": [1]},
        headers=student,
    )
    scores = [
        {"key": key, "score": 80}
        for key in ["content_creation", "cross_culture", "ecommerce", "ai_tools", "analytics"]
    ]

    # 学生不能批改
    resp = client.post(
        "/api/v1/works/1/review", json={"criterion_scores": scores}, headers=student
    )
    assert resp.status_code == 403

    # 非发布教师不能批改任务作品
    resp = client.post(
        "/api/v1/works/1/review", json={"criterion_scores": scores}, headers=teacher2
    )
    assert resp.status_code == 403

    # 重复提交冲突
    resp = client.post(
        f"/api/v1/tasks/{task_id}/submit", json={"work_ids": [1]}, headers=student
    )
    assert resp.status_code == 409

    # 学生看不到提交列表
    resp = client.get(f"/api/v1/tasks/{task_id}/submissions", headers=student)
    assert resp.status_code == 403


def test_rubric_validation_and_task_close(client):
    teacher = _h(_token(client, "w6teacher", "teacher123"))
    # 非法维度被拒
    resp = client.post(
        "/api/v1/tasks",
        json={
            "title": "非法 Rubric 任务",
            "rubric": {
                "criteria": [
                    {"key": "x", "name": "X", "dimension": "不存在的维度", "weight": 1}
                ]
            },
        },
        headers=teacher,
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == 40001

    # 自定义 Rubric 权重自动归一化
    resp = client.post(
        "/api/v1/tasks",
        json={
            "title": "自定义权重任务",
            "rubric": {
                "criteria": [
                    {"key": "a", "name": "内容", "dimension": "内容创作", "weight": 3},
                    {"key": "b", "name": "AI", "dimension": "AI工具应用", "weight": 1},
                ],
                "pass_score": 70,
            },
        },
        headers=teacher,
    )
    rubric = resp.json()["data"]["rubric_json"]
    assert rubric["criteria"][0]["weight"] == 0.75
    assert rubric["criteria"][1]["weight"] == 0.25
    task_id = resp.json()["data"]["id"]

    # 截止后学生不可提交
    resp = client.post(f"/api/v1/tasks/{task_id}/close", headers=teacher)
    assert resp.json()["data"]["status"] == "closed"
    student = _h(_token(client, "w6student", "student123"))
    resp = client.post(
        f"/api/v1/tasks/{task_id}/submit", json={"work_ids": [1]}, headers=student
    )
    assert resp.status_code == 409
    # 已截止任务不在学生列表
    resp = client.get("/api/v1/tasks", headers=student)
    assert all(item["status"] == "published" for item in resp.json()["data"]["items"])
