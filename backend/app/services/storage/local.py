"""本地磁盘存储驱动（开发默认）。

文件落在 LOCAL_STORAGE_PATH 下；get_url 返回走 API 流式端点的相对路径，
供前端带 token 拉取（GET /api/v1/files/{key}）。
"""
from pathlib import Path

from app.services.storage.base import StorageError, validate_key


class LocalStorage:
    def __init__(self, root: str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        validate_key(key)
        return self.root / key

    def put(self, key: str, data: bytes, mime: str) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def get_bytes(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise StorageError(f"文件不存在：{key}")
        return path.read_bytes()

    def get_url(self, key: str, expire: int = 3600) -> str:
        validate_key(key)
        return f"/api/v1/files/{key}"

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.is_file():
            path.unlink()

    def get_path(self, key: str) -> str:
        """本地绝对路径，供 ffmpeg 等外部进程直接读取（W4 用）。"""
        return str(self._path(key))

    def stat(self, key: str) -> int:
        path = self._path(key)
        if not path.is_file():
            raise StorageError(f"文件不存在：{key}")
        return path.stat().st_size

    def iter_bytes(self, key: str, offset: int = 0, length: int | None = None):
        """磁盘分块流式读取：大文件不整包进内存，支持 Range 偏移。"""
        path = self._path(key)
        if not path.is_file():
            raise StorageError(f"文件不存在：{key}")
        remaining = length
        with path.open("rb") as f:
            if offset:
                f.seek(offset)
            while remaining is None or remaining > 0:
                chunk_size = 256 * 1024 if remaining is None else min(256 * 1024, remaining)
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                if remaining is not None:
                    remaining -= len(chunk)
                yield chunk
