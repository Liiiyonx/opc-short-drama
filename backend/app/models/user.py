"""用户主表：三端 + 管理员统一账号体系。"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

ROLE_STUDENT = "student"
ROLE_TEACHER = "teacher"
ROLE_ENTERPRISE = "enterprise"
ROLE_ADMIN = "admin"
ROLES = (ROLE_STUDENT, ROLE_TEACHER, ROLE_ENTERPRISE, ROLE_ADMIN)

# SQLite 只有 INTEGER PRIMARY KEY 才是 rowid 别名（自增生效）；
# MySQL 保持 BIGINT。with_variant 让同一份模型兼容两种库。
PK_BIGINT = BigInteger().with_variant(Integer, "sqlite")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default=ROLE_STUDENT)
    status: Mapped[int] = mapped_column(Integer, default=1)  # 1 正常 / 0 禁用
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
