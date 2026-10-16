"""智能体会话与调用日志（成本核算与审计核心）。"""
from datetime import datetime

from sqlalchemy import (
    DECIMAL,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JSONType
from app.models.user import PK_BIGINT


class AgentSession(Base):
    __tablename__ = "agent_sessions"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    work_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("works.id"), nullable=True, index=True
    )
    agent_type: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="running", index=True)
    input_json: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    output_json: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AgentCallLog(Base):
    __tablename__ = "agent_call_logs"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    session_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("agent_sessions.id"), nullable=True
    )
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    agent_type: Mapped[str] = mapped_column(String(30))
    provider: Mapped[str] = mapped_column(String(50), default="")
    model: Mapped[str] = mapped_column(String(50), default="")
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    cost_est: Mapped[float] = mapped_column(DECIMAL(10, 4), default=0)
    status: Mapped[str] = mapped_column(String(20))
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_agent_call_logs_agent_type_created_at", "agent_type", "created_at"),
        Index("ix_agent_call_logs_user_id_created_at", "user_id", "created_at"),
    )
