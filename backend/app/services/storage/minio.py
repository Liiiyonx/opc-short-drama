"""MinIO 存储驱动（生产）。

S3 兼容自托管；get_url 返回预签名 URL（默认 1 小时有效）。
"""
import io

from app.services.storage.base import StorageError


class MinIOStorage:
    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool = False,
    ):
        from minio import Minio

        self.bucket = bucket
        self.client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        if not self.client.bucket_exists(bucket):
            self.client.make_bucket(bucket)

    def put(self, key: str, data: bytes, mime: str) -> str:
        self.client.put_object(
            self.bucket,
            key,
            io.BytesIO(data),
            length=len(data),
            content_type=mime,
        )
        return key

    def get_bytes(self, key: str) -> bytes:
        response = self.client.get_object(self.bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def stat(self, key: str) -> int:
        try:
            return self.client.stat_object(self.bucket, key).size
        except Exception as exc:  # noqa: BLE001 统一转 StorageError（S3Error 等）
            raise StorageError(f"文件不存在：{key}") from exc

    def iter_bytes(self, key: str, offset: int = 0, length: int | None = None):
        """对象分块流式下载（服务端 Range 代理；不占大内存）。"""
        response = self.client.get_object(
            self.bucket, key, offset=offset, length=length or 0
        )
        try:
            for chunk in response.stream(256 * 1024):
                yield chunk
        finally:
            response.close()
            response.release_conn()

    def get_url(self, key: str, expire: int = 3600) -> str:
        return self.client.presigned_get_object(
            self.bucket, key, expires=expire
        )

    def delete(self, key: str) -> None:
        self.client.remove_object(self.bucket, key)
