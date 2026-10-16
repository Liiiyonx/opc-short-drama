"""作品 / 资产 / 文件 API 全流程测试（W3）。

TestClient + 临时 SQLite（NullPool 避免跨事件循环复用连接）
+ LLM_PROVIDER=mock 测试桩，无需真实密钥。
"""
import asyncio
import os

os.environ["LLM_PROVIDER"] = "mock"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401  注册全部模型
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
                    username="w1student",
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
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    get_settings.cache_clear()
    get_storage.cache_clear()

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    get_settings.cache_clear()
    get_storage.cache_clear()


def _login(client: TestClient) -> str:
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "w1student", "password": "student123"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["access_token"]


def test_full_work_workflow(client):
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    # 1. 创建剧本作品（draft）
    resp = client.post(
        "/api/v1/works", json={"title": "测试剧", "type": "script"}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    script_work = resp.json()["data"]
    assert script_work["status"] == "draft"
    assert script_work["version"] == 1

    # 2. 生成剧本（mock 桩）
    resp = client.post(
        f"/api/v1/works/{script_work['id']}/generate",
        json={
            "genre": "逆袭",
            "target_market": "北美",
            "episodes": 2,
            "episode_minutes": 2,
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["work"]["status"] == "ready"
    outline = data["result"]
    assert outline["episodes"][0]["title"]

    # 3. 分镜作品：从剧本生成第 1 集分镜
    resp = client.post(
        "/api/v1/works", json={"title": "测试剧-分镜", "type": "storyboard"}, headers=headers
    )
    sb_work = resp.json()["data"]
    resp = client.post(
        f"/api/v1/works/{sb_work['id']}/generate",
        json={"source_work_id": script_work["id"], "episode": 1},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    shots = resp.json()["data"]["result"]["shots"]
    assert len(shots) == 3
    assert shots[0]["visual_prompt"]

    # 4. 详情：json 资产 + 访问 URL
    resp = client.get(f"/api/v1/works/{sb_work['id']}", headers=headers)
    detail = resp.json()["data"]
    assert len(detail["assets"]) == 1
    assert detail["assets"][0]["kind"] == "json"
    assert detail["assets"][0]["url"].startswith("/api/v1/files/")

    # 5. 再次生成 → 版本 2（parent 链）
    resp = client.post(
        f"/api/v1/works/{sb_work['id']}/generate",
        json={"source_work_id": script_work["id"], "episode": 1},
        headers=headers,
    )
    v2 = resp.json()["data"]["work"]
    assert v2["version"] == 2
    assert v2["parent_id"] == sb_work["id"]

    # 6. 流式拉取文件
    resp = client.get(detail["assets"][0]["url"], headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")

    # 7. 上传文件资产并拉取
    resp = client.post(
        f"/api/v1/works/{script_work['id']}/assets",
        files={"file": ("poster.png", b"\x89PNG\r\n\x1a\nfake-bytes", "image/png")},
        data={"kind": "image"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    uploaded = resp.json()["data"]
    resp = client.get(uploaded["url"], headers=headers)
    assert resp.status_code == 200
    assert resp.content == b"\x89PNG\r\n\x1a\nfake-bytes"

    # 8. AI 使用声明
    resp = client.post(
        f"/api/v1/works/{script_work['id']}/ai-declare",
        json={"agents_used": ["script"], "human_edit_ratio": 0.3},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["ai_declare_json"]["agents_used"] == ["script"]

    # 9. 列表
    resp = client.get("/api/v1/works?type=script", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 1


def test_storyboard_requires_source(client):
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post(
        "/api/v1/works", json={"title": "无源分镜", "type": "storyboard"}, headers=headers
    )
    work_id = resp.json()["data"]["id"]
    resp = client.post(
        f"/api/v1/works/{work_id}/generate", json={"episode": 1}, headers=headers
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == 40001


def test_storyboard_episode_out_of_range(client):
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    script = client.post(
        "/api/v1/works", json={"title": "剧", "type": "script"}, headers=headers
    ).json()["data"]
    client.post(
        f"/api/v1/works/{script['id']}/generate",
        json={"genre": "逆袭", "target_market": "北美", "episodes": 2},
        headers=headers,
    )
    sb = client.post(
        "/api/v1/works", json={"title": "分镜", "type": "storyboard"}, headers=headers
    ).json()["data"]
    resp = client.post(
        f"/api/v1/works/{sb['id']}/generate",
        json={"source_work_id": script["id"], "episode": 99},
        headers=headers,
    )
    assert resp.status_code == 422
    assert "episode" in resp.json()["message"]


def test_files_requires_auth(client):
    resp = client.get("/api/v1/files/works/1/json/x.json")
    assert resp.status_code == 401
