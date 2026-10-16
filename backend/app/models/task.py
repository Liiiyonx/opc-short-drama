"""实训任务域模型：任务 / 提交 / 组队（docs/03 §2）。"""
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

TASK_STATUS = ("draft", "published", "closed")
TEAM_RULES = ("free", "cross_major", "forced")
SUBMISSION_STATUS = ("submitted", "reviewed", "returned")


class TrainingTask(Base):
    __tablename__ = "training_tasks"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    course_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("courses.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200))
    brief: Mapped[str | None] = mapped_column(Text, nullable=True)
    rubric_json: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    team_rule: Mapped[str] = mapped_column(String(20), default="free")
    deliverable_json: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    creator_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (Index("ix_training_tasks_status_deadline", "status", "deadline"),)


class TaskSubmission(Base):
    __tablename__ = "task_submissions"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("training_tasks.id"), index=True
    )
    submitter_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    work_ids_json: Mapped[list | None] = mapped_column(JSONType, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="submitted")
    submitted_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_task_submissions_task_submitter", "task_id", "submitter_id"),
    )


class TeamMember(Base):
    __tablename__ = "team_members"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("training_tasks.id"))
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    role_in_team: Mapped[str] = mapped_column(String(20), default="content")

    __table_args__ = (
        UniqueConstraint("task_id", "user_id", name="uq_team_members_task_user"),
    )
