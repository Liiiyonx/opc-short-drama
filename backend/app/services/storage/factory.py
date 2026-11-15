"""存储工厂：按 STORAGE_BACKEND 返回驱动实例（local / minio）。"""
from functools import lru_cache

from app.core.config import get_settings
from app.services.storage.base import Storage


@lru_cache
def get_storage() -> Storage:
    settings = get_settings()
    if settings.storage_backend == "minio":
        from app.services.storage.minio import MinIOStorage

        return MinIOStorage(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            bucket=settings.minio_bucket,
            secure=settings.minio_secure,
        )
    from app.services.storage.local import LocalStorage

    return LocalStorage(settings.local_storage_path)
