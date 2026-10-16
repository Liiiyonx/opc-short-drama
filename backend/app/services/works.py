"""作品与资产业务服务（W3）。

规则：
- 版本链：首次生成原地升级（draft→ready）；再次生成创建 parent 链新版本；
- 文件全部走 Storage 抽象，库内只存 storage_key；
- 所有操作校验归属（本人或管理员）。
"""
import json

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import invoke_agent
from app.models.user import User
from app.models.work import WORK_TYPES, Work, WorkAsset
from app.schemas.work import GenerateIn
from app.services.storage.base import generate_key
from app.services.storage.factory import get_storage
from app.services.tts.voices import market_to_lang
from app.services.work_store import (
    latest_asset,
    latest_json_asset as _latest_json_asset,
    load_my_work as _load_my_work,
    save_asset,
)


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=404, detail={"code": 40401, "message": "作品不存在"}
    )


async def create_work(
    db: AsyncSession,
    user: User,
    title: str,
    type_: str,
    task_id: int | None = None,
) -> Work:
    if type_ not in WORK_TYPES:
        raise HTTPException(
            status_code=422,
            detail={"code": 40001, "message": f"不支持的作品类型：{type_}"},
        )
    work = Work(
        title=title,
        type=type_,
        task_id=task_id,
        owner_type="user",
        owner_id=user.id,
        created_by=user.id,
        status="draft",
        version=1,
    )
    db.add(work)
    await db.commit()
    await db.refresh(work)
    return work


async def list_works(
    db: AsyncSession,
    user: User,
    type_: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Work], int]:
    stmt = select(Work).where(Work.created_by == user.id)
    if type_:
        stmt = stmt.where(Work.type == type_)
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()
    rows = (
        (
            await db.execute(
                stmt.order_by(Work.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    return list(rows), int(total)


async def get_work_detail(
    db: AsyncSession, user: User, work_id: int
) -> tuple[Work, list[WorkAsset], list[Work]]:
    # 只读详情：教师可查看学生作品（批改需要）
    work = await _load_my_work(db, user, work_id, write=False)
    assets = (
        (
            await db.execute(
                select(WorkAsset)
                .where(WorkAsset.work_id == work_id)
                .order_by(WorkAsset.id)
            )
        )
        .scalars()
        .all()
    )
    versions = (
        (
            await db.execute(
                select(Work).where(Work.parent_id == work_id).order_by(Work.version)
            )
        )
        .scalars()
        .all()
    )
    return work, list(assets), list(versions)


def _meta_for(work: Work, result: dict, body: GenerateIn) -> dict:
    data = result["result"]
    if work.type == "script":
        return {
            "title": data.get("title"),
            "target_market": data.get("target_market"),
            "episodes": len(data.get("episodes", [])),
        }
    return {
        "source_work_id": body.source_work_id,
        "episode": body.episode or 1,
        "shots": len(data.get("shots", [])),
    }


async def _save_result_asset(
    db: AsyncSession, work: Work, result: dict
) -> WorkAsset:
    content = json.dumps(result, ensure_ascii=False).encode("utf-8")
    key = generate_key(f"works/{work.id}/json", "output.json")
    get_storage().put(key, content, "application/json")
    asset = WorkAsset(
        work_id=work.id,
        kind="json",
        storage_key=key,
        mime="application/json",
        size=len(content),
    )
    db.add(asset)
    await db.flush()
    return asset


async def generate(
    db: AsyncSession, user: User, work_id: int, body: GenerateIn
) -> tuple[Work, dict]:
    work = await _load_my_work(db, user, work_id)

    if work.type == "script":
        payload = body.model_dump(exclude_none=True)
        agent_type = "script"
    elif work.type == "storyboard":
        if body.source_work_id is None:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": 40001,
                    "message": "分镜生成需要 source_work_id（剧本作品 id）",
                },
            )
        source = await _load_my_work(db, user, body.source_work_id)
        if source.type != "script":
            raise HTTPException(
                status_code=422,
                detail={"code": 40001, "message": "source_work_id 必须是剧本作品"},
            )
        outline = await _latest_json_asset(db, source.id)
        if outline is None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": 40901,
                    "message": "源剧本还没有生成产物，请先对剧本执行生成",
                },
            )
        episodes = outline.get("episodes") or []
        episode = body.episode or 1
        if not 1 <= episode <= len(episodes):
            raise HTTPException(
                status_code=422,
                detail={
                    "code": 40001,
                    "message": f"episode 超出范围（当前 1-{len(episodes)}）",
                },
            )
        payload = {
            "episode_script": episodes[episode - 1],
            "aspect_ratio": body.aspect_ratio or "9:16",
            "style_hint": body.style_hint,
            "target_seconds": body.target_seconds or 120,
        }
        agent_type = "storyboard"
    elif work.type == "audio":
        # 从分镜作品提取台词行 → 配音（异步）
        if body.storyboard_work_id is None:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": 40001,
                    "message": "配音生成需要 storyboard_work_id（分镜作品 id）",
                },
            )
        storyboard = await _load_my_work(db, user, body.storyboard_work_id)
        if storyboard.type != "storyboard":
            raise HTTPException(
                status_code=422,
                detail={"code": 40001, "message": "storyboard_work_id 必须是分镜作品"},
            )
        shots_data = await _latest_json_asset(db, storyboard.id)
        if not shots_data or not shots_data.get("shots"):
            raise HTTPException(
                status_code=409,
                detail={"code": 40901, "message": "分镜作品没有产物，请先执行分镜生成"},
            )
        lang = body.lang or market_to_lang(
            (storyboard.meta_json or {}).get("target_market")
        )
        lines = [
            {
                "line_id": shot.get("shot_no", index + 1),
                "role": "narrator",
                "text": shot.get("dialogue", ""),
                "lang": lang,
            }
            for index, shot in enumerate(shots_data["shots"])
            if shot.get("dialogue")
        ]
        if not lines:
            raise HTTPException(
                status_code=422,
                detail={"code": 40001, "message": "分镜中没有台词，无法配音"},
            )
        payload = {"lines": lines, "voice_map": body.voice_map}
        agent_type = "tts"
    elif work.type == "subtitle":
        # 从配音作品复制 SRT（同步，供人工校轴）
        if body.audio_work_id is None:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": 40001,
                    "message": "字幕生成需要 audio_work_id（配音作品 id）",
                },
            )
        audio_work = await _load_my_work(db, user, body.audio_work_id)
        srt_asset = await latest_asset(db, audio_work.id, "srt")
        if srt_asset is None:
            raise HTTPException(
                status_code=409,
                detail={"code": 40901, "message": "配音作品没有 SRT，请先执行配音生成"},
            )
        srt_text = get_storage().get_bytes(srt_asset.storage_key).decode("utf-8")
        await save_asset(db, work.id, "srt", srt_text.encode("utf-8"), "text/plain")
        work.status = "ready"
        work.meta_json = {"source_work_id": body.audio_work_id}
        await db.commit()
        await db.refresh(work)
        return work, {"session_id": None, "agent_type": None, "result": {"copied": True}}
    elif work.type == "video":
        # 分镜图 + 配音 + SRT → 烧字幕 MP4（异步）
        if body.storyboard_work_id is None or body.audio_work_id is None:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": 40001,
                    "message": "视频生成需要 storyboard_work_id 与 audio_work_id",
                },
            )
        payload = {
            "storyboard_work_id": body.storyboard_work_id,
            "audio_work_id": body.audio_work_id,
            "width": body.width or 720,
            "height": body.height or 1280,
        }
        agent_type = "compose"
    else:
        raise HTTPException(
            status_code=409,
            detail={
                "code": 40901,
                "message": f"{work.type} 类型作品的生成尚未实现",
            },
        )

    result = await invoke_agent(agent_type, payload, user=user, db=db, work_id=work.id)

    if result.get("async"):
        # 异步智能体：作品置 generating，worker 完成后推进为 ready
        work.status = "generating"
        await db.commit()
        return work, result

    if work.status == "draft" and work.version == 1:
        target = work
        target.status = "ready"
        target.meta_json = _meta_for(work, result, body)
    else:
        target = Work(
            owner_type=work.owner_type,
            owner_id=work.owner_id,
            task_id=work.task_id,
            title=work.title,
            type=work.type,
            version=work.version + 1,
            parent_id=work.id,
            status="ready",
            meta_json=_meta_for(work, result, body),
            created_by=user.id,
        )
        db.add(target)
        await db.flush()

    await _save_result_asset(db, target, result["result"])
    await db.commit()
    await db.refresh(target)
    return target, result


async def add_file_asset(
    db: AsyncSession,
    user: User,
    work_id: int,
    kind: str,
    filename: str,
    data: bytes,
    mime: str | None,
) -> WorkAsset:
    work = await _load_my_work(db, user, work_id)
    key = generate_key(f"works/{work.id}/{kind}", filename or "upload.bin")
    get_storage().put(key, data, mime or "application/octet-stream")
    asset = WorkAsset(
        work_id=work.id,
        kind=kind,
        storage_key=key,
        mime=mime,
        size=len(data),
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return asset


async def set_ai_declare(
    db: AsyncSession, user: User, work_id: int, declare: dict
) -> Work:
    work = await _load_my_work(db, user, work_id)
    work.ai_declare_json = declare
    await db.commit()
    await db.refresh(work)
    return work


async def finalize_work_from_session(db: AsyncSession, session) -> None:
    """异步智能体结束后推进关联作品状态（arq worker 调用）。

    - success：资产已由智能体自身写入（ctx.work_id），这里只更新状态与摘要；
    - failed：作品从 generating 回落为 failed，避免前端永久等待。
    异步作品的再生成不建版本链（P1 项），资产按次追加。
    """
    if session.work_id is None:
        return
    work = (
        await db.execute(select(Work).where(Work.id == session.work_id))
    ).scalar_one_or_none()
    if work is None:
        return
    if session.status == "failed":
        if work.status == "generating":
            work.status = "failed"
            await db.commit()
        return
    if session.status != "success" or work.status == "ready":
        return
    result = session.output_json or {}
    work.status = "ready"
    if work.type == "audio":
        work.meta_json = {
            "lines": len(result.get("assets", [])),
            "total_duration_ms": result.get("total_duration_ms", 0),
            "srt_key": result.get("srt_key"),
        }
    elif work.type == "video":
        work.meta_json = {
            "images_used": result.get("images_used", 0),
            "placeholder": result.get("placeholder", False),
            "duration_ms": result.get("duration_ms", 0),
            "video_key": result.get("video_key"),
        }
    await db.commit()
