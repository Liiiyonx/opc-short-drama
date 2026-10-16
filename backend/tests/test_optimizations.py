"""极致优化专项测试（2026-10-16）：

- extract_json：代码块 / 尾随逗号 / 前后杂文 / 截断取首对象
- chat_json：首轮坏 JSON → 自动修复重试（usage 累计两次）
- TTS 并行合成：顺序与输入一致（SRT 时间轴正确）
- 卡死会话清扫：超时 running → failed + 作品 generating → failed
- finalize_work_from_session：失败回落 / 成功推进
"""
import os

os.environ["TTS_PROVIDER"] = "mock"
os.environ["LLM_PROVIDER"] = "mock"

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
from app.agents.base import AgentContext
from app.agents.orchestrator import sweep_stale_sessions
from app.agents.tts_agent import TTSAgent, TTSInput, TTSLine
from app.core.config import get_settings
from app.core.security import hash_password
from app.db.base import Base
from app.models.agent import AgentSession
from app.models.user import User
from app.models.work import Work
from app.services.llm.client import LLMError, LLMReply, chat_json, extract_json
from app.services.storage.factory import get_storage
from app.services.works import finalize_work_from_session


def _utcnow() -> datetime:
    """与业务代码一致的 naive UTC（见 orchestrator._now）。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.fixture
async def db(tmp_path, monkeypatch):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path}/test.db", poolclass=NullPool
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path / "storage"))
    monkeypatch.setenv("TTS_PROVIDER", "mock")
    get_settings.cache_clear()
    get_storage.cache_clear()
    async with factory() as session:
        user = User(
            username="opttester",
            password_hash=hash_password("test123456"),
            role="student",
            status=1,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        yield session, user
    get_storage.cache_clear()
    get_settings.cache_clear()
    await engine.dispose()


# ---------- extract_json 容错 ----------


def test_extract_json_tolerances():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('这里是结果：{"a": 1} 以上。') == {"a": 1}
    # 尾随逗号（模型常见瑕疵）
    assert extract_json('{"a": 1, "b": [1, 2,],}') == {"a": 1, "b": [1, 2]}
    # JSON 后跟解释文本 → raw_decode 取首个完整对象
    assert extract_json('{"a": 1}\n\n补充说明：以上为结果') == {"a": 1}
    # 嵌套 + 代码块 + 尾随文本
    nested = '```json\n{"shots": [{"shot_no": 1}], "note": "ok",}\n```\n完毕'
    assert extract_json(nested)["shots"][0]["shot_no"] == 1
    with pytest.raises(LLMError):
        extract_json("完全不是 JSON 的一段话")


# ---------- chat_json 修复重试 ----------


async def test_chat_json_repair_roundtrip(monkeypatch):
    calls: list[str] = []

    async def fake_completion(system, user, agent_type, *, json_mode=True):
        calls.append(user)
        if len(calls) == 1:
            return LLMReply(
                content="开头解释 {broken json",
                usage={
                    "provider": "test",
                    "model": "m",
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                },
            )
        return LLMReply(
            content='{"ok": true}',
            usage={
                "provider": "test",
                "model": "m",
                "prompt_tokens": 20,
                "completion_tokens": 3,
            },
        )

    monkeypatch.setattr(
        "app.services.llm.client.chat_completion", fake_completion
    )
    data, usage = await chat_json("sys", "原始请求", "script")
    assert data == {"ok": True}
    assert len(calls) == 2
    assert usage["prompt_tokens"] == 30  # 累计两次调用
    assert usage["completion_tokens"] == 8
    assert usage["repair_roundtrip"] is True
    assert "不是合法 JSON" in calls[1]  # 修复提示词确实发出


async def test_chat_json_happy_path_no_repair(monkeypatch):
    calls = []

    async def fake_completion(system, user, agent_type, *, json_mode=True):
        calls.append(user)
        return LLMReply(
            content='{"a": 1}',
            usage={
                "provider": "test",
                "model": "m",
                "prompt_tokens": 7,
                "completion_tokens": 2,
            },
        )

    monkeypatch.setattr(
        "app.services.llm.client.chat_completion", fake_completion
    )
    data, usage = await chat_json("sys", "u", "script")
    assert data == {"a": 1}
    assert len(calls) == 1
    assert "repair_roundtrip" not in usage


# ---------- TTS 并行合成保序 ----------


async def test_tts_parallel_preserves_order(db):
    session, user = db
    work = Work(
        title="保序测试",
        type="audio",
        owner_type="user",
        owner_id=user.id,
        created_by=user.id,
        status="draft",
        version=1,
    )
    session.add(work)
    await session.flush()

    lines = [
        TTSLine(line_id=1, text="短", lang="zh-CN"),
        TTSLine(line_id=2, text="中等长度的台词内容", lang="zh-CN"),
        TTSLine(line_id=3, text="哦", lang="zh-CN"),
        TTSLine(line_id=4, text="较长的第四句台词用来验证顺序仍然正确", lang="zh-CN"),
    ]
    ctx = AgentContext(db=session, user=user, work_id=work.id, session_id=0)
    output = await TTSAgent().run(TTSInput(lines=lines), ctx)

    # 资产顺序 = 输入顺序（SRT 时间轴因此正确）
    assert [asset.line_id for asset in output.assets] == [1, 2, 3, 4]
    srt_text = get_storage().get_bytes(output.srt_key).decode("utf-8")
    first_cue = srt_text.split("\n\n")[0]
    assert "短" in first_cue  # 第 1 行对应第 1 个 cue
    # 时间轴自 0 开始且累加
    assert "00:00:00,000 --> " in first_cue


# ---------- 卡死会话清扫 ----------


async def test_sweep_stale_sessions(db, monkeypatch):
    session, user = db
    monkeypatch.setenv("AGENT_TASK_TIMEOUT_SECONDS", "60")
    get_settings.cache_clear()

    work = Work(
        title="卡死作品",
        type="video",
        owner_type="user",
        owner_id=user.id,
        created_by=user.id,
        status="generating",
        version=1,
    )
    session.add(work)
    await session.flush()

    stale = AgentSession(
        user_id=user.id,
        work_id=work.id,
        agent_type="compose",
        status="running",
        input_json={},
        created_at=_utcnow() - timedelta(hours=2),
    )
    fresh = AgentSession(
        user_id=user.id,
        work_id=None,
        agent_type="tts",
        status="running",
        input_json={},
        created_at=_utcnow(),
    )
    session.add_all([stale, fresh])
    await session.commit()

    cleaned = await sweep_stale_sessions(session)
    assert cleaned == 1  # 只清超时的，不动新鲜的

    await session.refresh(stale)
    await session.refresh(fresh)
    await session.refresh(work)
    assert stale.status == "failed"
    assert "任务超时" in stale.error
    assert work.status == "failed"  # 作品联动回落
    assert fresh.status == "running"  # 正常任务不被误杀

    # 指定 session_id 的惰性清扫：新鲜任务不会被动
    assert await sweep_stale_sessions(session, session_id=fresh.id) == 0
    get_settings.cache_clear()


# ---------- finalize 失败回落 ----------


async def test_finalize_work_on_failed_session(db):
    session, user = db
    work = Work(
        title="失败回落",
        type="audio",
        owner_type="user",
        owner_id=user.id,
        created_by=user.id,
        status="generating",
        version=1,
    )
    session.add(work)
    await session.flush()
    agent_session = AgentSession(
        user_id=user.id,
        work_id=work.id,
        agent_type="tts",
        status="failed",
        input_json={},
    )
    session.add(agent_session)
    await session.commit()

    await finalize_work_from_session(session, agent_session)
    await session.refresh(work)
    assert work.status == "failed"

    # 成功路径不受影响
    agent_session.status = "success"
    agent_session.output_json = {
        "assets": [{"line_id": 1}],
        "total_duration_ms": 1200,
        "srt_key": "k",
    }
    work.status = "generating"
    await session.commit()
    await finalize_work_from_session(session, agent_session)
    await session.refresh(work)
    assert work.status == "ready"
    assert work.meta_json["lines"] == 1


async def test_agent_tasks_poll_idempotent_after_finalize(db):
    """已终结会话不再被清扫逻辑改动。"""
    session, user = db
    done = AgentSession(
        user_id=user.id,
        agent_type="tts",
        status="success",
        input_json={},
        created_at=_utcnow() - timedelta(hours=3),
    )
    session.add(done)
    await session.commit()
    assert await sweep_stale_sessions(session) == 0
    rows = (
        (await session.execute(select(AgentSession).where(AgentSession.id == done.id)))
        .scalars()
        .all()
    )
    assert rows[0].status == "success"
