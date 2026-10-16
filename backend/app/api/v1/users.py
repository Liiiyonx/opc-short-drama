"""用户：我的信息 / 用户管理（管理员，W1）。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from app.core.deps import CurrentUser, DbSession, require_role
from app.core.responses import ok
from app.core.security import hash_password
from app.models.profile import (
    EnterpriseProfile,
    StudentProfile,
    TeacherProfile,
)
from app.models.user import User
from app.schemas.user import UserCreate, UserOut

router = APIRouter(prefix="/users", tags=["用户"])


@router.get("/me", summary="当前用户信息 + 角色档案")
async def get_me(user: CurrentUser, db: DbSession):
    profile = None
    if user.role == "student":
        row = (
            await db.execute(
                select(StudentProfile).where(StudentProfile.user_id == user.id)
            )
        ).scalar_one_or_none()
        if row:
            profile = {
                "major": row.major,
                "grade": row.grade,
                "ability_json": row.ability_json,
            }
    elif user.role == "teacher":
        row = (
            await db.execute(
                select(TeacherProfile).where(TeacherProfile.user_id == user.id)
            )
        ).scalar_one_or_none()
        if row:
            profile = {"college": row.college, "title": row.title}
    elif user.role == "enterprise":
        row = (
            await db.execute(
                select(EnterpriseProfile).where(
                    EnterpriseProfile.user_id == user.id
                )
            )
        ).scalar_one_or_none()
        if row:
            profile = {
                "company_name": row.company_name,
                "verify_status": row.verify_status,
                "license_no": row.license_no,
                "contact_name": row.contact_name,
                "contact_phone": row.contact_phone,
            }
    return ok(
        {
            "id": user.id,
            "username": user.username,
            "phone": user.phone,
            "role": user.role,
            "status": user.status,
            "created_at": user.created_at,
            "profile": profile,
        }
    )


@router.get(
    "",
    summary="用户列表（管理员）",
    dependencies=[Depends(require_role("admin"))],
)
async def list_users(
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    total = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    rows = (
        (
            await db.execute(
                select(User)
                .order_by(User.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    items = [UserOut.model_validate(row).model_dump() for row in rows]
    return ok({"items": items, "total": total, "page": page, "page_size": page_size})


@router.post(
    "",
    summary="创建用户（管理员）",
    dependencies=[Depends(require_role("admin"))],
)
async def create_user(body: UserCreate, db: DbSession):
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
    await db.commit()
    await db.refresh(user)
    return ok(UserOut.model_validate(user).model_dump(), "创建成功")
