"""课程基础接口：列表（任务绑定用）+ 创建（管理后台）。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession, require_role
from app.core.responses import ok
from app.models.course import Course, CourseClass
from app.schemas.course import CourseCreateIn

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


@router.post(
    "",
    summary="创建课程（管理员）",
    dependencies=[Depends(require_role("admin"))],
)
async def create_course(body: CourseCreateIn, db: DbSession):
    exists = (
        await db.execute(select(Course).where(Course.code == body.code))
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(
            status_code=409, detail={"code": 40901, "message": "课程代码已存在"}
        )
    course = Course(
        code=body.code,
        name=body.name,
        semester=body.semester,
        teacher_id=body.teacher_id,
    )
    db.add(course)
    await db.flush()
    for class_name in body.class_names:
        if class_name.strip():
            db.add(CourseClass(course_id=course.id, name=class_name.strip()))
    await db.commit()
    await db.refresh(course)
    return ok(
        {"id": course.id, "code": course.code, "name": course.name},
        "课程已创建",
    )
