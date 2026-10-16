"""认证入参。"""
from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=64)


class RegisterIn(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=6, max_length=64)
    role: str = Field(default="student", pattern="^(student|teacher|enterprise)$")
    phone: str | None = Field(default=None, max_length=20)
    # 档案字段（按角色选用，其余忽略）
    major: str | None = None
    grade: str | None = None
    college: str | None = None
    title: str | None = None
    company_name: str | None = None


class RefreshIn(BaseModel):
    refresh_token: str
