"""认证：注册 / 登录 / 刷新（W1）。

P0-02 权限收紧：仅学生可自助注册；教师/企业账号由管理员创建
（管理员创建的企业默认视为已认证）。登录失败防爆破：内存滑窗限流。
"""
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import DbSession, unauthorized
from app.core.ratelimit import (
    check_login_allowed,
    login_key,
    record_login_failure,
    record_login_success,
)
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


@router.post("/register", summary="注册（仅学生自助；教师/企业联系管理员开通）")
async def register(body: RegisterIn, db: DbSession):
    # P0-02 红线：任何人都不能通过公开注册直接获得教师/企业等高权限身份
    if body.role != "student":
        raise HTTPException(
            status_code=403,
            detail={
                "code": 40301,
                "message": "仅支持学生自助注册；教师/企业账号请联系平台管理员开通",
            },
        )
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
async def login(body: LoginIn, request: Request, db: DbSession):
    key = login_key(body.username, request.client.host if request.client else "unknown")
    check_login_allowed(key)
    user = (
        await db.execute(select(User).where(User.username == body.username))
    ).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        record_login_failure(key)
        raise unauthorized("账号或密码错误")
    if user.status != 1:
        raise HTTPException(
            status_code=403, detail={"code": 40301, "message": "账号已被禁用"}
        )
    record_login_success(key)
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
