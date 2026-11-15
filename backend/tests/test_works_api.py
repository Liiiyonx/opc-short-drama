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


def test_upload_rejects_bad_extension(client):
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    work = client.post(
        "/api/v1/works", json={"title": "剧", "type": "script"}, headers=headers
    ).json()["data"]
    resp = client.post(
        f"/api/v1/works/{work['id']}/assets",
        files={"file": ("payload.exe", b"MZ...", "application/octet-stream")},
        data={"kind": "image"},
        headers=headers,
    )
    assert resp.status_code == 422
    assert "文件类型" in resp.json()["message"]


def test_upload_rejects_oversize(client, monkeypatch):
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    monkeypatch.setenv("UPLOAD_MAX_MB", "1")
    get_settings.cache_clear()
    try:
        work = client.post(
            "/api/v1/works", json={"title": "剧", "type": "script"}, headers=headers
        ).json()["data"]
        resp = client.post(
            f"/api/v1/works/{work['id']}/assets",
            files={"file": ("big.png", b"x" * (2 * 1024 * 1024), "image/png")},
            data={"kind": "image"},
            headers=headers,
        )
        assert resp.status_code == 413
        assert "上限" in resp.json()["message"]
    finally:
        monkeypatch.delenv("UPLOAD_MAX_MB")
        get_settings.cache_clear()


def test_file_range_requests(client):
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    work = client.post(
        "/api/v1/works", json={"title": "剧", "type": "script"}, headers=headers
    ).json()["data"]
    body = bytes(range(256)) * 4  # 1024 字节
    resp = client.post(
        f"/api/v1/works/{work['id']}/assets",
        files={"file": ("range-test.png", body, "image/png")},
        data={"kind": "image"},
        headers=headers,
    )
    url = resp.json()["data"]["url"]

    # 整文件
    resp = client.get(url, headers=headers)
    assert resp.status_code == 200
    assert resp.content == body
    assert resp.headers["accept-ranges"] == "bytes"

    # 单段 Range：bytes=0-9
    resp = client.get(url, headers={**headers, "Range": "bytes=0-9"})
    assert resp.status_code == 206
    assert resp.content == body[:10]
    assert resp.headers["content-range"] == f"bytes 0-9/{len(body)}"

    # 开区间：bytes=1000-
    resp = client.get(url, headers={**headers, "Range": "bytes=1000-"})
    assert resp.status_code == 206
    assert resp.content == body[1000:]

    # 尾部：bytes=-24
    resp = client.get(url, headers={**headers, "Range": "bytes=-24"})
    assert resp.status_code == 206
    assert resp.content == body[-24:]

    # 起点越界 → 416
    resp = client.get(url, headers={**headers, "Range": "bytes=999999-"})
    assert resp.status_code == 416


def test_audio_lang_backtracks_to_script_market(client, monkeypatch):
    """北美剧本 → 分镜 → 配音：不传 lang 应回溯 en-US（修复：原实现永远 zh-CN）。"""
    from app.services import works as works_service

    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    script = client.post(
        "/api/v1/works", json={"title": "剧", "type": "script"}, headers=headers
    ).json()["data"]
    client.post(
        f"/api/v1/works/{script['id']}/generate",
        json={"genre": "逆袭", "target_market": "北美", "episodes": 1},
        headers=headers,
    )
    sb = client.post(
        "/api/v1/works", json={"title": "分镜", "type": "storyboard"}, headers=headers
    ).json()["data"]
    client.post(
        f"/api/v1/works/{sb['id']}/generate",
        json={"source_work_id": script["id"], "episode": 1},
        headers=headers,
    )
    # 数据血缘：分镜 meta 补记目标市场
    sb_detail = client.get(f"/api/v1/works/{sb['id']}", headers=headers).json()["data"]
    assert sb_detail["work"]["meta_json"]["target_market"] == "北美"

    # 只拦截 tts（异步智能体，测试环境无 Redis），其余走真实 mock 调用
    from app.agents.orchestrator import invoke_agent as real_invoke

    captured = {}

    async def fake_invoke(agent_type, payload, user, db, work_id=None):
        if agent_type != "tts":
            return await real_invoke(
                agent_type, payload, user=user, db=db, work_id=work_id
            )
        captured["payload"] = payload
        return {
            "session_id": 999,
            "agent_type": agent_type,
            "async": True,
            "status": "running",
        }

    monkeypatch.setattr(works_service, "invoke_agent", fake_invoke)
    audio = client.post(
        "/api/v1/works", json={"title": "配音", "type": "audio"}, headers=headers
    ).json()["data"]
    resp = client.post(
        f"/api/v1/works/{audio['id']}/generate",
        json={"storyboard_work_id": sb["id"]},  # 不传 lang → 回溯市场
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert captured["payload"]["lines"], "应提取台词行"
    assert captured["payload"]["lines"][0]["lang"] == "en-US"
