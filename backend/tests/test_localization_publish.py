"""翻译本地化 / 发布参数 / 人工修订比对 测试（2026-10-16 全面优化轮）。

- translate：作品生成链路（台词提取 → mock 本地化 → 文案/合规标记落库）
- publish：成片 → 发布参数包（落 publish_params 资产）
- revision：字幕修订 → difflib 实测修改度 → 回写 AI 声明
- review：批改优先采用实测修改度（教学红线闭环）
"""
import os

os.environ["TTS_PROVIDER"] = "mock"
os.environ["LLM_PROVIDER"] = "mock"

import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
from app.core.config import get_settings
from app.core.security import hash_password
from app.db.base import Base
from app.models.user import User
from app.models.work import Work, WorkAsset
from app.schemas.task import CriterionScore, ReviewIn
from app.schemas.work import GenerateIn, PublishParamsIn, RevisionIn
from app.services import tasks as tasks_service
from app.services import works as works_service
from app.services.storage.factory import get_storage
from app.services.work_store import save_asset


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
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    get_settings.cache_clear()
    get_storage.cache_clear()
    async with factory() as session:
        student = User(
            username="loc_student",
            password_hash=hash_password("test123456"),
            role="student",
            status=1,
        )
        teacher = User(
            username="loc_teacher",
            password_hash=hash_password("test123456"),
            role="teacher",
            status=1,
        )
        session.add_all([student, teacher])
        await session.commit()
        await session.refresh(student)
        await session.refresh(teacher)
        yield session, student, teacher
    get_storage.cache_clear()
    get_settings.cache_clear()
    await engine.dispose()


async def _make_work(session, user, type_, title, status="draft", meta=None):
    work = Work(
        title=title,
        type=type_,
        owner_type="user",
        owner_id=user.id,
        created_by=user.id,
        status=status,
        version=1,
        meta_json=meta or {},
    )
    session.add(work)
    await session.flush()
    return work


# ---------- 翻译本地化 ----------


async def test_translate_works_flow(db):
    session, student, _ = db
    script = await _make_work(
        session, student, "script", "翻译-剧本", status="ready",
        meta={"target_market": "北美", "title": "The Secret"},
    )
    storyboard = await _make_work(
        session, student, "storyboard", "翻译-分镜", status="ready",
        meta={"source_work_id": script.id},
    )
    shots = {
        "shots": [
            {"shot_no": 1, "dialogue": "你的餐。"},
            {"shot_no": 2, "dialogue": ""},
            {"shot_no": 3, "dialogue": "放地上，别过来。"},
        ]
    }
    await save_asset(
        session, storyboard.id, "json",
        json.dumps(shots, ensure_ascii=False).encode("utf-8"),
        "application/json",
    )
    translate = await _make_work(session, student, "translate", "翻译-翻译")
    work, result = await works_service.generate(
        session, student, translate.id,
        GenerateIn(storyboard_work_id=storyboard.id),
    )
    data = result["result"]
    # 台词提取：仅非空 2 行，line_id 与镜号一致
    assert [item["line_id"] for item in data["lines"]] == [1, 3]
    # 市场沿链回溯 → 北美 → en-US
    assert data["target_locale"] == "en-US"
    assert work.status == "ready"
    assert work.meta_json["target_locale"] == "en-US"
    assert work.meta_json["lines"] == 2
    # 产物 JSON 落库
    assets = (
        (await session.execute(select(WorkAsset).where(WorkAsset.work_id == work.id)))
        .scalars()
        .all()
    )
    assert any(asset.kind == "json" for asset in assets)


# ---------- 发布参数 ----------


async def test_publish_params_flow(db):
    session, student, _ = db
    script = await _make_work(
        session, student, "script", "发布-剧本", status="ready",
        meta={"target_market": "北美"},
    )
    await save_asset(
        session, script.id, "json",
        json.dumps(
            {"title": "The Secret", "logline": "外卖箱里的秘密。", "episodes": []},
            ensure_ascii=False,
        ).encode("utf-8"),
        "application/json",
    )
    video = await _make_work(
        session, student, "video", "发布-成片", status="ready",
        meta={"duration_ms": 16800},
    )
    work, result = await works_service.generate_publish_params(
        session, student, video.id, PublishParamsIn(source_work_id=script.id)
    )
    data = result["result"]
    assert len(data["platforms"]) == 3
    assert data["compliance_checklist"]
    assets = (
        (await session.execute(select(WorkAsset).where(WorkAsset.work_id == work.id)))
        .scalars()
        .all()
    )
    assert any(asset.kind == "publish_params" for asset in assets)


async def test_publish_params_rejects_non_video(db):
    session, student, _ = db
    script = await _make_work(session, student, "script", "发布-非视频", status="ready")
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await works_service.generate_publish_params(
            session, student, script.id, PublishParamsIn()
        )
    assert exc.value.status_code == 409


# ---------- 人工修订（初终稿差异） ----------


async def test_submit_revision_measures_edit_ratio(db):
    session, student, _ = db
    work = await _make_work(session, student, "subtitle", "修订-字幕", status="ready")
    srt = (
        "1\n00:00:00,000 --> 00:00:01,500\n你的餐。\n\n"
        "2\n00:00:01,500 --> 00:00:03,000\n放地上，别过来。\n"
    )
    await save_asset(session, work.id, "srt", srt.encode("utf-8"), "text/plain")

    # 完全相同 → 修改度 0
    result = await works_service.submit_revision(
        session, student, work.id, RevisionIn(kind="srt", content=srt)
    )
    assert result["measured_edit_ratio"] == 0.0

    # 大幅改写 → 修改度 > 0 且写入声明
    revised = srt.replace("你的餐。", "这是您点的外卖。").replace(
        "放地上，别过来。", "请放在门口，不要靠近。"
    )
    result2 = await works_service.submit_revision(
        session, student, work.id, RevisionIn(kind="srt", content=revised)
    )
    assert 0 < result2["measured_edit_ratio"] < 1
    await session.refresh(work)
    assert work.ai_declare_json["measured_edit_ratio"] == result2["measured_edit_ratio"]
    # 修订产物落库（srt_revised）
    assets = (
        (await session.execute(select(WorkAsset).where(WorkAsset.work_id == work.id)))
        .scalars()
        .all()
    )
    assert any(asset.kind == "srt_revised" for asset in assets)


# ---------- 批改优先采用实测修改度 ----------


async def test_review_prefers_measured_edit_ratio(db):
    session, student, teacher = db
    work = await _make_work(
        session, student, "script", "批改-作品", status="ready",
        meta={"title": "X", "target_market": "北美", "episodes": 1},
    )
    work.ai_declare_json = {
        "agents_used": ["script"],
        "human_edit_ratio": 0.1,  # 自报
        "measured_edit_ratio": 0.55,  # 实测
    }
    await session.commit()

    scores = [
        CriterionScore(key="content_creation", score=85),
        CriterionScore(key="cross_culture", score=80),
        CriterionScore(key="ecommerce", score=75),
        CriterionScore(key="ai_tools", score=90),
        CriterionScore(key="analytics", score=70),
    ]
    data = await tasks_service.review_work(
        session, teacher, work.id, ReviewIn(criterion_scores=scores, comment="测试")
    )
    review = data["review"]
    assert float(review.ai_diff_ratio) == 0.55  # 实测优先
    assert review.rubric_score_json["edit_ratio_source"] == "measured"
    assert 70 < data["total"] < 90  # 加权总分在合理区间
