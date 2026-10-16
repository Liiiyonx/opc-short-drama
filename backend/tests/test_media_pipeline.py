"""W4 媒体服务与异步链路测试。

- media：SRT 生成/解析、静音生成、时长探测、拼接、占位图、烧字幕
- TTS Agent（mock 桩）：逐行音频 + 合并 + SRT + 资产落库
- compose Agent（占位图路线）：分镜 + 配音 → MP4
- 异步链路：invoke 入队 → execute_session 执行 → 会话成功（需 Redis）
"""
import os

os.environ["TTS_PROVIDER"] = "mock"
os.environ["LLM_PROVIDER"] = "mock"

import json
import shutil

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
from app.agents.base import AgentContext
from app.agents.compose_agent import ComposeAgent, ComposeInput
from app.agents.orchestrator import execute_session, invoke_agent
from app.agents.tts_agent import TTSAgent, TTSInput, TTSLine
from app.core.config import get_settings
from app.core.security import hash_password
from app.db.base import Base
from app.models.agent import AgentSession
from app.models.user import User
from app.models.work import Work, WorkAsset
from app.services.media import (
    _parse_srt_cues,
    build_srt,
    burn_video,
    concat_audio,
    placeholder_png,
    probe_duration_ms,
    render_silence_mp3,
)
from app.services.storage.factory import get_storage
from app.services.work_store import save_asset

requires_ffmpeg = pytest.mark.skipif(
    not shutil.which("ffmpeg"), reason="ffmpeg 不可用"
)


def _redis_ok() -> bool:
    try:
        import redis

        client = redis.Redis(
            host="127.0.0.1", port=6379, db=1, socket_timeout=2, protocol=2
        )
        return bool(client.ping())
    except Exception:
        return False


requires_redis = pytest.mark.skipif(not _redis_ok(), reason="Redis 不可用")


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
            username="w4tester",
            password_hash=hash_password("test123456"),
            role="student",
            status=1,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        yield session, user, factory
    get_storage.cache_clear()
    get_settings.cache_clear()
    await engine.dispose()


async def _make_work(session, user, type_, title):
    work = Work(
        title=title,
        type=type_,
        owner_type="user",
        owner_id=user.id,
        created_by=user.id,
        status="draft",
        version=1,
    )
    session.add(work)
    await session.flush()
    return work


@requires_ffmpeg
def test_media_helpers():
    srt = build_srt(
        [
            {"start_ms": 0, "end_ms": 1500, "text": "你好"},
            {"start_ms": 1500, "end_ms": 3200, "text": "世界"},
        ]
    )
    assert "00:00:00,000 --> 00:00:01,500" in srt
    assert "1\n" in srt
    assert _parse_srt_cues(srt) == [(0, 1500), (1500, 3200)]

    silence = render_silence_mp3(2.0)
    assert 1800 <= probe_duration_ms(silence, ".mp3") <= 2300

    merged = concat_audio([silence, silence])
    assert 3800 <= probe_duration_ms(merged, ".mp3") <= 4300

    assert len(placeholder_png(0)) > 100


@requires_ffmpeg
def test_burn_video_smoke():
    audio = render_silence_mp3(3.0)
    srt = build_srt(
        [
            {"start_ms": 0, "end_ms": 1500, "text": "第一镜"},
            {"start_ms": 1500, "end_ms": 3000, "text": "第二镜"},
        ]
    )
    images = [placeholder_png(index) for index in range(2)]
    video = burn_video(images, audio, srt)
    assert b"ftyp" in video[:16]
    assert probe_duration_ms(video, ".mp4") >= 2800


async def test_tts_agent_mock_chain(db):
    session, user, _ = db
    work = await _make_work(session, user, "audio", "配音作品")
    ctx = AgentContext(db=session, user=user, work_id=work.id, session_id=0)
    payload = TTSInput(
        lines=[
            TTSLine(line_id=1, role="narrator", text="你好世界", lang="zh-CN"),
            TTSLine(line_id=2, role="narrator", text="第二句台词", lang="zh-CN"),
        ]
    )
    output = await TTSAgent().run(payload, ctx)

    assert len(output.assets) == 2
    assert output.merged_audio_key and output.srt_key
    assert output.total_duration_ms >= 2000

    srt_text = get_storage().get_bytes(output.srt_key).decode("utf-8")
    assert "你好世界" in srt_text
    assert "00:00:01,000 --> " in srt_text

    assets = (
        (
            await session.execute(
                select(WorkAsset).where(WorkAsset.work_id == work.id)
            )
        )
        .scalars()
        .all()
    )
    assert sorted(asset.kind for asset in assets) == [
        "audio",
        "audio",
        "audio_merged",
        "srt",
    ]


@requires_ffmpeg
async def test_compose_agent_placeholder(db):
    session, user, _ = db
    storyboard = await _make_work(session, user, "storyboard", "分镜作品")
    shots = {
        "shots": [
            {
                "shot_no": 1,
                "scene": 1,
                "shot_size": "特写",
                "camera_move": "固定",
                "visual_prompt": "close-up test",
                "dialogue": "你好",
                "duration_sec": 5,
            },
            {
                "shot_no": 2,
                "scene": 1,
                "shot_size": "中景",
                "camera_move": "推",
                "visual_prompt": "medium shot test",
                "dialogue": "世界",
                "duration_sec": 5,
            },
        ]
    }
    await save_asset(
        session,
        storyboard.id,
        "json",
        json.dumps(shots, ensure_ascii=False).encode("utf-8"),
        "application/json",
    )

    audio_work = await _make_work(session, user, "audio", "配音作品")
    ctx_tts = AgentContext(db=session, user=user, work_id=audio_work.id, session_id=0)
    await TTSAgent().run(
        TTSInput(
            lines=[
                TTSLine(line_id=1, text="你好"),
                TTSLine(line_id=2, text="世界"),
            ]
        ),
        ctx_tts,
    )

    video_work = await _make_work(session, user, "video", "成片作品")
    ctx = AgentContext(db=session, user=user, work_id=video_work.id, session_id=0)
    output = await ComposeAgent().run(
        ComposeInput(storyboard_work_id=storyboard.id, audio_work_id=audio_work.id),
        ctx,
    )
    assert output.placeholder is True
    assert output.images_used == 2
    assert output.video_key
    assert output.duration_ms >= 1800

    video_bytes = get_storage().get_bytes(output.video_key)
    assert b"ftyp" in video_bytes[:16]


@requires_redis
async def test_async_flow_enqueue_and_execute(db, monkeypatch):
    session, user, factory = db
    result = await invoke_agent(
        "tts",
        {
            "lines": [
                {"line_id": 1, "role": "narrator", "text": "异步测试台词", "lang": "zh-CN"}
            ]
        },
        user=user,
        db=session,
        work_id=None,
    )
    assert result["async"] is True
    assert result["status"] == "running"
    session_id = result["session_id"]

    # 本测试直接调 execute_session 模拟 worker（不常驻 worker 进程），
    # 并把 worker 的会话工厂指向临时库
    monkeypatch.setattr(
        "app.agents.orchestrator.AsyncSessionLocal", factory
    )
    import redis

    client = redis.Redis(host="127.0.0.1", port=6379, db=1, protocol=2)
    client.delete("arq:queue")

    await execute_session(session_id)

    session.expire_all()
    agent_session = (
        await session.execute(
            select(AgentSession).where(AgentSession.id == session_id)
        )
    ).scalar_one()
    assert agent_session.status == "success"
    assert agent_session.output_json["total_duration_ms"] >= 1000
    assert agent_session.output_json["srt_key"]
