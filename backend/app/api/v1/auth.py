"""认证：注册 / 登录 / 刷新（W1）。

P0 开放注册（无邀请码），P1 再加审核流。
"""
import jwt
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import DbSession, unauthorized
from app.core.responses import ok
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.profile import (
    EnterpriseProfile,
    StudentProfile,
    TeacherProfile,
)
from app.models.user import User
from app.schemas.auth import LoginIn, RefreshIn, RegisterIn

router = APIRouter(prefix="/auth", tags=["认证"])


def _issue_tokens(user: User) -> dict:
    return {
        "access_token": create_access_token(user.id, user.role),
        "refresh_token": create_refresh_token(user.id),
        "token_type": "bearer",
        "user": {"id": user.id, "username": user.username, "role": user.role},
    }


async def _create_profile(db: AsyncSession, user: User, body: RegisterIn) -> None:
    if body.role == "student":
        db.add(
            StudentProfile(user_id=user.id, major=body.major, grade=body.grade)
        )
    elif body.role == "teacher":
        db.add(
            TeacherProfile(user_id=user.id, college=body.college, title=body.title)
        )
    elif body.role == "enterprise":
        db.add(
            EnterpriseProfile(
                user_id=user.id,
                company_name=body.company_name or body.username,
            )
        )


@router.post("/register", summary="注册（P0 开放）")
async def register(body: RegisterIn, db: DbSession):
    exists = (
        await db.execute(select(User).where(User.username == body.username))
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(
            status_code=409, detail={"code": 40901, "message": "用户名已存在"}
        )
    user = User(
        username=body.username,
        phone=body.phone,
        password_hash=hash_password(body.password),
        role=body.role,
        status=1,
    )
    db.add(user)
    await db.flush()
    await _create_profile(db, user, body)
    await db.commit()
    await db.refresh(user)
    return ok(_issue_tokens(user), "注册成功")


@router.post("/login", summary="三端统一登录")
async def login(body: LoginIn, db: DbSession):
    user = (
        await db.execute(select(User).where(User.username == body.username))
    ).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise unauthorized("账号或密码错误")
    if user.status != 1:
        raise HTTPException(
            status_code=403, detail={"code": 40301, "message": "账号已被禁用"}
        )
    return ok(_issue_tokens(user))


@router.post("/refresh", summary="刷新 access token")
async def refresh(body: RefreshIn, db: DbSession):
    try:
        payload = decode_token(body.refresh_token)
    except jwt.PyJWTError:
        raise unauthorized("refresh token 无效")
    if payload.get("type") != "refresh":
        raise unauthorized("token 类型错误")
    user = (
        await db.execute(select(User).where(User.id == int(payload["sub"])))
    ).scalar_one_or_none()
    if user is None or user.status != 1:
        raise unauthorized("用户不存在或已禁用")
    return ok(
        {
            "access_token": create_access_token(user.id, user.role),
            "token_type": "bearer",
        }
    )
