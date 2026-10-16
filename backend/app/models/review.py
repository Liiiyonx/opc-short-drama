"""批改记录与能力快照（docs/03 §3、§4）。"""
from datetime import datetime

from sqlalchemy import (
    DECIMAL,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JSONType
from app.models.user import PK_BIGINT

# 五维能力（固定枚举，与 docs/03 §4 一致）
ABILITY_DIMENSIONS = (
    "内容创作",
    "跨文化沟通",
    "电商运营",
    "AI工具应用",
    "数据分析",
)

ABILITY_SOURCES = ("review", "agent_quality", "order", "analytics")


class WorkReview(Base):
    __tablename__ = "work_reviews"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    work_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("works.id"), index=True
    )
    teacher_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), index=True
    )
    rubric_score_json: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    # AI 初稿与学生终稿差异度 = 学生申报的人工修改比例（0-1）
    ai_diff_ratio: Mapped[float | None] = mapped_column(DECIMAL(4, 3), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AbilitySnapshot(Base):
    """能力分只追加不改写；成长曲线由快照聚合（事件溯源）。"""

    __tablename__ = "ability_snapshots"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    dimension: Mapped[str] = mapped_column(String(20))
    score: Mapped[float] = mapped_column(DECIMAL(5, 2))
    source: Mapped[str] = mapped_column(String(20))
    ref_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index(
            "ix_ability_snapshots_student_dim_created",
            "student_id",
            "dimension",
            "created_at",
        ),
    )
