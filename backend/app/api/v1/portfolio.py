"""作品集：脱敏对外分享（学生）+ 公开只读视图（免登录）。

- POST /portfolio/share（学生）：获取/创建分享令牌，返回 /share/{token} 路径；
- GET  /portfolio/public/{token}（免登录）：脱敏视图——代号而非用户名，
  仅暴露作品元信息（标题/类型/状态），不含文件与联系方式。
"""
import secrets

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession
from app.core.responses import ok
from app.models.profile import StudentProfile
from app.models.user import User
from app.models.work import Work

router = APIRouter(prefix="/portfolio", tags=["作品集"])

_TYPE_LABELS = {
    "script": "剧本",
    "storyboard": "分镜",
    "translate": "翻译本地化",
    "audio": "配音",
    "subtitle": "字幕",
    "video": "成片",
}


def _alias_for(user: User) -> str:
    return f"同学#{str(user.id).zfill(4)}"


@router.post("/share", summary="获取/创建我的作品集分享链接")
async def create_share(user: CurrentUser, db: DbSession):
    if user.role != "student":
        raise HTTPException(
            status_code=403, detail={"code": 40301, "message": "只有学生可以分享作品集"}
        )
    profile = (
        await db.execute(
            select(StudentProfile).where(StudentProfile.user_id == user.id)
        )
    ).scalar_one_or_none()
    if profile is None:
        raise HTTPException(
            status_code=404, detail={"code": 40401, "message": "学生档案不存在"}
        )
    if not profile.portfolio_token:
        profile.portfolio_token = secrets.token_hex(16)
        await db.commit()
    return ok({"token": profile.portfolio_token, "path": f"/share/{profile.portfolio_token}"})


@router.get("/public/{token}", summary="公开作品集视图（脱敏，免登录）")
async def public_portfolio(token: str, db: DbSession):
    profile = (
        await db.execute(
            select(StudentProfile).where(StudentProfile.portfolio_token == token)
        )
    ).scalar_one_or_none()
    if profile is None:
        raise HTTPException(
            status_code=404, detail={"code": 40401, "message": "分享链接不存在或已失效"}
        )
    user = (
        await db.execute(select(User).where(User.id == profile.user_id))
    ).scalar_one_or_none()
    if user is None or user.status != 1:
        raise HTTPException(
            status_code=404, detail={"code": 40401, "message": "分享链接不存在或已失效"}
        )

    works = (
        (
            await db.execute(
                select(Work)
                .where(Work.created_by == user.id, Work.status == "ready")
                .order_by(Work.id.desc())
                .limit(12)
            )
        )
        .scalars()
        .all()
    )
    return ok(
        {
            "alias": _alias_for(user),
            "major": profile.major,
            "grade": profile.grade,
            "works": [
                {
                    "title": w.title,
                    "type": w.type,
                    "type_label": _TYPE_LABELS.get(w.type, w.type),
                    "version": w.version,
                    "created_at": w.created_at,
                }
                for w in works
            ],
        }
    )
