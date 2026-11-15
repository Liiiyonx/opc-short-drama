"""能力图谱 API（W6）：个人五维能力 + 成长曲线 / 班级分布 / 预警。"""
from fastapi import APIRouter, Depends, Query

from app.core.deps import CurrentUser, DbSession, require_role
from app.core.responses import ok
from app.models.profile import StudentProfile
from app.models.user import User
from app.services import ability as ability_service
from app.services.ability import latest_scores_by_students
from sqlalchemy import select

router = APIRouter(prefix="/ability", tags=["能力图谱"])


@router.get("/students/{student_id}", summary="个人五维能力 + 成长曲线")
async def get_student_ability(student_id: int, user: CurrentUser, db: DbSession):
    data = await ability_service.get_student_ability(db, user, student_id)
    for point in data["history"]:
        if point.get("created_at") is not None:
            point["created_at"] = point["created_at"].isoformat()
    return ok(data)


@router.get("/classes/{class_id}", summary="班级能力分布")
async def get_class_ability(class_id: int, user: CurrentUser, db: DbSession):
    data = await ability_service.get_class_ability(db, user, class_id)
    return ok(data)


@router.get(
    "/warnings",
    summary="能力预警（均分低于达标线 / 无评分数据的学生）",
    dependencies=[Depends(require_role("teacher", "admin"))],
)
async def ability_warnings(
    user: CurrentUser,
    db: DbSession,
    threshold: float = Query(default=60, gt=0, le=100),
):
    """连续低分学生的简单预警：按五维最新分均分升序，含无数据学生。"""
    rows = (
        (
            await db.execute(
                select(User, StudentProfile)
                .join(StudentProfile, StudentProfile.user_id == User.id)
                .where(User.role == "student", User.status == 1)
            )
        )
        .all()
    )
    ability_map = await latest_scores_by_students(
        db, [u.id for u, _ in rows]
    )

    items = []
    for u, p in rows:
        dims = ability_map.get(u.id, {})
        if not dims:
            items.append(
                {
                    "username": u.username,
                    "major": p.major,
                    "grade": p.grade,
                    "avg": None,
                    "weak": [],
                    "issue": "暂无能力评分数据（尚未被批改过作品）",
                }
            )
            continue
        avg = round(sum(dims.values()) / len(dims), 1)
        weak = [d for d, v in dims.items() if v < threshold]
        if avg < threshold:
            items.append(
                {
                    "username": u.username,
                    "major": p.major,
                    "grade": p.grade,
                    "avg": avg,
                    "weak": weak,
                    "issue": f"五维均分 {avg} 低于达标线 {threshold:g}"
                    + (f"，薄弱：{'、'.join(weak)}" if weak else ""),
                }
            )
    # 有数据且分低的排前，无数据的殿后
    items.sort(key=lambda x: (x["avg"] is None, x["avg"] if x["avg"] is not None else 999))
    return ok({"threshold": threshold, "count": len(items), "items": items[:20]})
