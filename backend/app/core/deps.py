"""FastAPI 依赖：数据库会话、当前用户、角色守卫。"""
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import User

bearer = HTTPBearer(auto_error=False)


def unauthorized(message: str = "未登录或登录已过期") -> HTTPException:
    return HTTPException(status_code=401, detail={"code": 40101, "message": message})


def forbidden(message: str = "无权限执行该操作") -> HTTPException:
    return HTTPException(status_code=403, detail={"code": 40301, "message": message})


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if credentials is None:
        raise unauthorized()
    try:
        payload = decode_token(credentials.credentials)
    except jwt.PyJWTError:
        raise unauthorized()
    if payload.get("type") != "access":
        raise unauthorized("token 类型错误，请使用 access token")
    user = (
        await db.execute(select(User).where(User.id == int(payload["sub"])))
    ).scalar_one_or_none()
    if user is None:
        raise unauthorized("用户不存在")
    if user.status != 1:
        raise forbidden("账号已被禁用")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[AsyncSession, Depends(get_db)]


def require_role(*roles: str):
    """角色守卫：require_role("teacher", "admin")。"""

    async def checker(user: CurrentUser) -> User:
        if user.role not in roles:
            raise forbidden()
        return user

    return checker
