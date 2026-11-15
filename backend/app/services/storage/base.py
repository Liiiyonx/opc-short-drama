"""存储抽象基类：Protocol、键校验、键生成。

实现方（Local / MinIO）对业务层透明；库内只存 storage_key。
键规范：works/{work_id}/{kind}/{uuid}{ext}
"""
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol
from uuid import uuid4

_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_\-./]+$")


class StorageError(Exception):
    """存储层错误（非法键、文件不存在等）。"""


def validate_key(key: str) -> str:
    """防目录穿越：拒绝 ..、绝对路径与非法字符。"""
    if not key or key.startswith("/") or ".." in key or "\\" in key:
        raise StorageError(f"非法存储键：{key}")
    if not _KEY_PATTERN.match(key):
        raise StorageError(f"非法存储键：{key}")
    return key


def generate_key(prefix: str, filename: str) -> str:
    ext = Path(filename).suffix.lower()[:10]
    return f"{prefix.strip('/')}/{uuid4().hex}{ext}"


class Storage(Protocol):
    def put(self, key: str, data: bytes, mime: str) -> str: ...

    def get_bytes(self, key: str) -> bytes: ...

    def get_url(self, key: str, expire: int = 3600) -> str: ...

    def delete(self, key: str) -> None: ...

    def stat(self, key: str) -> int:
        """文件字节数；不存在抛 StorageError。"""
        ...

    def iter_bytes(
        self, key: str, offset: int = 0, length: int | None = None
    ) -> Iterator[bytes]:
        """分块流式读取（offset/length 支撑 HTTP Range）；不存在抛 StorageError。"""
        ...
