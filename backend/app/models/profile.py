"""三角色档案：学生 / 教师 / 企业（与 users 一对一）。"""
from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JSONType

VERIFY_PENDING = "pending"
VERIFY_APPROVED = "approved"
VERIFY_REJECTED = "rejected"


class StudentProfile(Base):
    __tablename__ = "student_profiles"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), primary_key=True
    )
    major: Mapped[str | None] = mapped_column(String(50), nullable=True)
    grade: Mapped[str | None] = mapped_column(String(10), nullable=True)
    class_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("course_classes.id"), nullable=True
    )
    ability_json: Mapped[dict | None] = mapped_column(JSONType, nullable=True)


class TeacherProfile(Base):
    __tablename__ = "teacher_profiles"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), primary_key=True
    )
    college: Mapped[str | None] = mapped_column(String(100), nullable=True)
    title: Mapped[str | None] = mapped_column(String(50), nullable=True)


class EnterpriseProfile(Base):
    __tablename__ = "enterprise_profiles"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), primary_key=True
    )
    company_name: Mapped[str] = mapped_column(String(200))
    license_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    verify_status: Mapped[str] = mapped_column(String(20), default=VERIFY_PENDING)
    contact_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
