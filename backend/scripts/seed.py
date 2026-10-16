"""演示数据种子：四角色账号 + 课程 + 实训任务 + 工单。

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
from app.models.order import WorkOrder
from app.models.profile import (
    EnterpriseProfile,
    StudentProfile,
    TeacherProfile,
)
from app.models.task import TrainingTask
from app.models.user import User
from app.services.tasks import DEFAULT_RUBRIC

USERS = [
    ("admin", "admin123", "admin", None),
    ("teacher01", "teacher123", "teacher", None),
    ("student01", "student123", "student", "电子商务"),
    ("student02", "student123", "student", "商务英语"),
    ("enterprise01", "ent123456", "enterprise", None),
]

COURSE_CODE = "CROSS201"
COURSE_NAME = "AIGC跨境内容创作"
DEMO_TASK_TITLE = "示范任务：短剧出海全流程实战"


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

            # 演示任务（published，含默认五项 Rubric）
            task = (
                await db.execute(
                    select(TrainingTask).where(TrainingTask.title == DEMO_TASK_TITLE)
                )
            ).scalar_one_or_none()
            if task is None:
                db.add(
                    TrainingTask(
                        course_id=course.id,
                        title=DEMO_TASK_TITLE,
                        brief="组队完成一部 2 集短剧出海全流程（剧本→分镜→配音→字幕→成片）并提交成片，教师按 Rubric 批改并更新五维能力。",
                        rubric_json=DEFAULT_RUBRIC,
                        team_rule="free",
                        deliverable_json={"items": ["成片 MP4", "字幕 SRT", "AI 使用声明"]},
                        status="published",
                        creator_id=teacher.id,
                    )
                )
                print(f"created demo task: {DEMO_TASK_TITLE}")

            # 演示工单（published，学生可直接投标）
            enterprise = (
                await db.execute(select(User).where(User.role == "enterprise"))
            ).scalars().first()
            if enterprise is not None:
                order = (
                    await db.execute(
                        select(WorkOrder).where(
                            WorkOrder.title == "演示工单：出海短剧《都市逆袭》定制"
                        )
                    )
                ).scalar_one_or_none()
                if order is None:
                    db.add(
                        WorkOrder(
                            enterprise_id=enterprise.id,
                            title="演示工单：出海短剧《都市逆袭》定制",
                            requirements_json={
                                "genre": "逆袭",
                                "market": "北美",
                                "episodes": 6,
                                "lang": "en-US",
                                "delivery": "成片 MP4 + 字幕 + 发布参数包",
                            },
                            budget_cents=300000,
                            status="published",
                            verify_note="演示数据：需求清晰，通过",
                        )
                    )
                    print("created demo order")
        await db.commit()
    print("seed done")


if __name__ == "__main__":
    asyncio.run(seed())
