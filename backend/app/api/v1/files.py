"""文件流式读取：GET /api/v1/files/{storage_key}。

local 后端直接读盘；minio 后端经客户端代理下载（也可让前端直接用预签名 URL）。
需要登录（Bearer token）；前端 <img>/<audio> 场景请用 fetch + blob（W5 处理）。
"""
import mimetypes

from fastapi import APIRouter, Response
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession
from app.services.storage.base import StorageError
from app.services.storage.factory import get_storage
from app.models.work import WorkAsset

router = APIRouter(prefix="/files", tags=["文件"])


@router.get("/{key:path}", summary="流式读取存储文件")
async def read_file(key: str, user: CurrentUser, db: DbSession):
    try:
        data = get_storage().get_bytes(key)
    except StorageError:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=404, detail={"code": 40401, "message": "文件不存在"}
        )
    asset = (
        await db.execute(
            select(WorkAsset).where(WorkAsset.storage_key == key)
        )
    ).scalar_one_or_none()
    mime = (
        (asset.mime if asset else None)
        or mimetypes.guess_type(key)[0]
        or "application/octet-stream"
    )
    return Response(content=data, media_type=mime)
