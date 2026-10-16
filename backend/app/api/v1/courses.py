"""课程基础接口（W6 轻量版）：列表供任务绑定使用。"""
from fastapi import APIRouter
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession
from app.core.responses import ok
from app.models.course import Course, CourseClass

router = APIRouter(prefix="/courses", tags=["课程"])


@router.get("", summary="课程列表")
async def list_courses(user: CurrentUser, db: DbSession):
    courses = (
        (await db.execute(select(Course).order_by(Course.id))).scalars().all()
    )
    items = []
    for course in courses:
        classes = (
            (
                await db.execute(
                    select(CourseClass).where(CourseClass.course_id == course.id)
                )
            )
            .scalars()
            .all()
        )
        items.append(
            {
                "id": course.id,
                "code": course.code,
                "name": course.name,
                "semester": course.semester,
                "classes": [
                    {"id": c.id, "name": c.name, "student_count": c.student_count}
                    for c in classes
                ],
            }
        )
    return ok({"items": items, "total": len(items)})
