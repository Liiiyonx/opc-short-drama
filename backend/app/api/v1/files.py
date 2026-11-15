"""文件流式读取：GET /api/v1/files/{storage_key}。

- 分块流式返回（local 磁盘 / minio 对象代理），大文件不整包进 API 内存；
- 支持单段 Range（视频拖动进度条必需）与 416；
- mime 扩展名优先（免查库），未知扩展再落库查资产记录。

local 后端 get_url 返回本端点相对路径，前端带 token 拉取；
minio 后端 get_url 返回预签名 URL（前端直连，绕过本进程）。
"""
import mimetypes

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession
from app.models.work import WorkAsset
from app.services.storage.base import StorageError
from app.services.storage.factory import get_storage

router = APIRouter(prefix="/files", tags=["文件"])

_UNSATISFIABLE = "unsatisfiable"


def _parse_range(header: str, size: int):
    """解析单段 Range 头。

    返回 (start, end) 闭区间；非法/多段返回 None（按整文件 200）；
    起点越界返回 _UNSATISFIABLE（416）。
    """
    if not header.startswith("bytes="):
        return None
    spec = header[len("bytes=") :].strip()
    if "," in spec or "-" not in spec:
        return None
    start_raw, _, end_raw = spec.partition("-")
    try:
        if start_raw == "":  # bytes=-N：最后 N 字节
            if not end_raw:
                return None
            n = int(end_raw)
            if n <= 0:
                return None
            start, end = max(0, size - n), size - 1
        else:
            start = int(start_raw)
            end = int(end_raw) if end_raw else size - 1
    except ValueError:
        return None
    if start >= size:
        return _UNSATISFIABLE
    if start < 0 or end < start:
        return None
    return start, min(end, size - 1)


@router.get("/{key:path}", summary="流式读取存储文件")
async def read_file(key: str, request: Request, user: CurrentUser, db: DbSession):
    storage = get_storage()
    try:
        size = storage.stat(key)
    except StorageError:
        raise HTTPException(
            status_code=404, detail={"code": 40401, "message": "文件不存在"}
        )

    # mime：扩展名优先（免查库），未知扩展落库查资产记录
    mime = mimetypes.guess_type(key)[0]
    if mime is None:
        asset = (
            await db.execute(
                select(WorkAsset).where(WorkAsset.storage_key == key)
            )
        ).scalar_one_or_none()
        mime = (asset.mime if asset else None) or "application/octet-stream"

    headers = {"Accept-Ranges": "bytes", "Content-Length": str(size)}
    status_code = 200
    start, end = 0, size - 1

    range_header = request.headers.get("range")
    if range_header:
        parsed = _parse_range(range_header, size)
        if parsed == _UNSATISFIABLE:
            return Response(
                status_code=416, headers={"Content-Range": f"bytes */{size}"}
            )
        if parsed is not None:
            start, end = parsed
            status_code = 206
            length = end - start + 1
            headers["Content-Range"] = f"bytes {start}-{end}/{size}"
            headers["Content-Length"] = str(length)

    def chunks():
        yield from storage.iter_bytes(key, offset=start, length=end - start + 1)

    return StreamingResponse(
        chunks(), status_code=status_code, media_type=mime, headers=headers
    )
