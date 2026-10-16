"""演示数据种子：四角色账号 + 一门课程 + 一个班级。

用法（在 backend/ 目录）：
    python -m scripts.seed

账号清单（P0 演示用，上线前必须改密或删除）：
    admin / admin123        管理员
    teacher01 / teacher123  教师（经济贸易学院）
    student01 / student123  学生（电子商务）
    student02 / student123  学生（商务英语）
    enterprise01 / ent123456  企业（已认证）
"""
import asyncio

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.course import Course, CourseClass
from app.models.profile import (
    EnterpriseProfile,
    StudentProfile,
    TeacherProfile,
)
from app.models.user import User

USERS = [
    ("admin", "admin123", "admin", None),
    ("teacher01", "teacher123", "teacher", None),
    ("student01", "student123", "student", "电子商务"),
    ("student02", "student123", "student", "商务英语"),
    ("enterprise01", "ent123456", "enterprise", None),
]

COURSE_CODE = "CROSS201"
COURSE_NAME = "AIGC跨境内容创作"


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        for username, password, role, major in USERS:
            exists = (
                await db.execute(select(User).where(User.username == username))
            ).scalar_one_or_none()
            if exists:
                print(f"skip {username}（已存在）")
                continue
            user = User(
                username=username,
                password_hash=hash_password(password),
                role=role,
                status=1,
            )
            db.add(user)
            await db.flush()
            if role == "student":
                db.add(
                    StudentProfile(
                        user_id=user.id, major=major, grade="2025"
                    )
                )
            elif role == "teacher":
                db.add(
                    TeacherProfile(
                        user_id=user.id, college="经济贸易学院", title="讲师"
                    )
                )
            elif role == "enterprise":
                db.add(
                    EnterpriseProfile(
                        user_id=user.id,
                        company_name="福州出海文化传媒有限公司",
                        license_no="91350100MA000000XX",
                        verify_status="approved",
                    )
                )
            print(f"created {username}（{role}）")

        teacher = (
            await db.execute(select(User).where(User.role == "teacher"))
        ).scalars().first()
        if teacher is not None:
            course = (
                await db.execute(select(Course).where(Course.code == COURSE_CODE))
            ).scalar_one_or_none()
            if course is None:
                course = Course(
                    code=COURSE_CODE,
                    name=COURSE_NAME,
                    teacher_id=teacher.id,
                    semester="2026-2027-1",
                )
                db.add(course)
                await db.flush()
                db.add(
                    CourseClass(
                        course_id=course.id,
                        name="电商+英语混编1班",
                        student_count=2,
                    )
                )
                print(f"created course {COURSE_CODE} {COURSE_NAME}")
        await db.commit()
    print("seed done")


if __name__ == "__main__":
    asyncio.run(seed())
