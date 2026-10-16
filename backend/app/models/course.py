"""课程与班级（W1 仅建表，业务在 W6 展开）。"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# 同 models/user.py：SQLite 渲染 INTEGER 以启用 rowid 自增
PK_BIGINT = BigInteger().with_variant(Integer, "sqlite")


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    teacher_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True
    )
    semester: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CourseClass(Base):
    __tablename__ = "course_classes"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("courses.id"))
    name: Mapped[str] = mapped_column(String(100))
    student_count: Mapped[int] = mapped_column(Integer, default=0)
