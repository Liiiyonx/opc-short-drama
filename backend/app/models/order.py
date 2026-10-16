"""工单交易域模型：企业工单 / 投标（docs/03 §4，P0 精简版）。

状态机：draft → pending_review → published → bidding → awarded → closed
（P0 不做合同/结算，验收结果先记 meta；支付一律线下，平台只存凭证）
"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JSONType
from app.models.user import PK_BIGINT

ORDER_STATUS = (
    "draft",
    "pending_review",
    "published",
    "bidding",
    "awarded",
    "closed",
    "cancelled",
)
BID_STATUS = ("active", "won", "lost", "withdrawn")


class WorkOrder(Base):
    __tablename__ = "work_orders"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    enterprise_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    requirements_json: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    budget_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    verify_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_work_orders_status_created", "status", "created_at"),
    )


class OrderBid(Base):
    __tablename__ = "order_bids"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("work_orders.id"), index=True
    )
    bidder_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), index=True
    )
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    proposal: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("order_id", "bidder_id", name="uq_order_bids_order_bidder"),
    )
