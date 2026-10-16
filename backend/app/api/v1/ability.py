"""能力图谱 API（W6）：个人五维能力 + 成长曲线 / 班级分布。"""
from fastapi import APIRouter

from app.core.deps import CurrentUser, DbSession
from app.core.responses import ok
from app.services import ability as ability_service

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
