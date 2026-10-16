"""作品与作品资产（W2 建表；作品 API 随 W3 资产能力一起上线）。

设计要点（docs/03）：
- 版本链：parent_id 指向上一版本，version 在链内递增；
- 文件与数据分离：库内只存 storage_key；
- task_id 暂不加外键（training_tasks 表 W6 建），到时补迁移。
"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JSONType

# 同 models/user.py：SQLite 渲染 INTEGER 以启用 rowid 自增
from app.models.user import PK_BIGINT  # noqa: F401  （供迁移引用一致性）

WORK_TYPES = ("script", "storyboard", "audio", "subtitle", "video")
WORK_STATUS = ("draft", "generating", "ready", "failed")


class Work(Base):
    __tablename__ = "works"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    owner_type: Mapped[str] = mapped_column(String(10), default="user")
    owner_id: Mapped[int] = mapped_column(BigInteger, index=True)
    task_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("training_tasks.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(20))
    version: Mapped[int] = mapped_column(Integer, default=1)
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("works.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="draft")
    ai_declare_json: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    meta_json: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    created_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_works_owner", "owner_type", "owner_id"),
        Index("ix_works_type_status", "type", "status"),
    )


class WorkAsset(Base):
    __tablename__ = "work_assets"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    work_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("works.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # text/image/audio/srt/video/json
    storage_key: Mapped[str] = mapped_column(String(500))
    mime: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
