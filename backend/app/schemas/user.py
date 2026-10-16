"""用户相关入参出参。"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["student", "teacher", "enterprise", "admin"]


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=6, max_length=64)
    role: Role = "student"
    phone: str | None = Field(default=None, max_length=20)


class UserStatusIn(BaseModel):
    """管理员启用 / 禁用用户（1=启用，0=禁用）。"""

    status: int = Field(ge=0, le=1)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    phone: str | None = None
    role: str
    status: int
    created_at: datetime | None = None
