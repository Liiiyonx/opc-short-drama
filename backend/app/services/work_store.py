"""作品/资产读写助手（works 服务与 compose Agent 共用）。

独立成模块避免循环导入：works → orchestrator → registry → compose_agent。
"""
import json

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.work import Work, WorkAsset
from app.services.storage.base import generate_key
from app.services.storage.factory import get_storage


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=404, detail={"code": 40401, "message": "作品不存在"}
    )


async def load_my_work(db: AsyncSession, user: User, work_id: int) -> Work:
    work = (
        await db.execute(select(Work).where(Work.id == work_id))
    ).scalar_one_or_none()
    if work is None or (work.created_by != user.id and user.role != "admin"):
        raise _not_found()
    return work


async def latest_json_asset(db: AsyncSession, work_id: int) -> dict | None:
    asset = (
        (
            await db.execute(
                select(WorkAsset)
                .where(WorkAsset.work_id == work_id, WorkAsset.kind == "json")
                .order_by(WorkAsset.id.desc())
            )
        )
        .scalars()
        .first()
    )
    if asset is None:
        return None
    raw = get_storage().get_bytes(asset.storage_key).decode("utf-8")
    return json.loads(raw)


async def latest_asset(
    db: AsyncSession, work_id: int, kind: str
) -> WorkAsset | None:
    return (
        (
            await db.execute(
                select(WorkAsset)
                .where(WorkAsset.work_id == work_id, WorkAsset.kind == kind)
                .order_by(WorkAsset.id.desc())
            )
        )
        .scalars()
        .first()
    )


async def list_assets(db: AsyncSession, work_id: int, kind: str) -> list[WorkAsset]:
    return list(
        (
            (
                await db.execute(
                    select(WorkAsset)
                    .where(WorkAsset.work_id == work_id, WorkAsset.kind == kind)
                    .order_by(WorkAsset.id)
                )
            )
            .scalars()
            .all()
        )
    )


async def save_asset(
    db: AsyncSession,
    work_id: int | None,
    kind: str,
    data: bytes,
    mime: str,
    duration_ms: int | None = None,
) -> tuple[WorkAsset | None, str]:
    """写存储 + 落库；返回 (资产行或 None, 存储键)。

    work_id 为空时只写存储（直调智能体场景），键照常返回。
    """
    prefix = f"works/{work_id}/{kind}" if work_id else f"tmp/{kind}"
    key = generate_key(prefix, f"asset.{kind}")
    get_storage().put(key, data, mime)
    if work_id is None:
        return None, key
    asset = WorkAsset(
        work_id=work_id,
        kind=kind,
        storage_key=key,
        mime=mime,
        size=len(data),
        duration_ms=duration_ms,
    )
    db.add(asset)
    await db.flush()
    return asset, key
