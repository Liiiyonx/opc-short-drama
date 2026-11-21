"""演示数据种子：四角色账号 + 课程 + 实训任务 + 工单 + 展示剧集。

用法（在 backend/ 目录）：
    python -m scripts.seed

账号清单（P0 演示用，上线前必须改密或删除）：
    admin / admin123        管理员
    teacher01 / teacher123  教师（经济贸易学院）
    student01 / student123  学生（电子商务）
    student02 / student123  学生（商务英语）
    enterprise01 / ent123456  企业（已认证）

P0-12/9.2 展示数据包：若 scenarios/ 存在已生成样片，会把样片作为
student01 的「展示剧集」成片落库（首次进入即有可播作品），并附带
五维能力快照与两张待审核工单，保证演示首屏不空、闭环可讲。
"""
import asyncio
import json
import shutil
from pathlib import Path

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
from app.models.review import AbilitySnapshot
from app.models.task import TrainingTask
from app.models.user import User
from app.models.work import Work, WorkAsset
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

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCENARIOS_ROOT = REPO_ROOT / "scenarios"

SHOWCASE_SCRIPT_TITLE = "展示剧集：《海潮女王的逆袭》剧本"
SHOWCASE_VIDEO_TITLE = "展示剧集：《海潮女王的逆袭》成片"

ABILITY_DEMO = [
    ("内容创作", 88),
    ("跨文化沟通", 82),
    ("电商运营", 79),
    ("AI工具应用", 90),
    ("数据分析", 76),
]

PENDING_ORDERS = [
    ("演示工单：宠物拟人微短剧《毛孩当家》", 260000,
     {"genre": "治愈", "market": "东南亚", "episodes": 4, "lang": "en-US",
      "delivery": "成片 MP4 + 双语字幕"}),
    ("演示工单：县域产业带好物剧《山货上星》", 320000,
     {"genre": "电商", "market": "北美", "episodes": 6, "lang": "en-US",
      "delivery": "成片 MP4 + 发布参数包"}),
]


def _pick_scenario() -> Path | None:
    """优先北美样片（答辩主线），其次任意已生成场景。"""
    for name in ("north-america-revenge", "culture-export", "southeast-asia-commerce"):
        candidate = SCENARIOS_ROOT / name
        if (candidate / "final.mp4").exists():
            return candidate
    if SCENARIOS_ROOT.exists():
        for candidate in sorted(SCENARIOS_ROOT.iterdir()):
            if (candidate / "final.mp4").exists():
                return candidate
    return None


def _scenario_duration_ms(scenario_dir: Path) -> int | None:
    report = scenario_dir / "qc-report.json"
    try:
        return int(json.loads(report.read_text(encoding="utf-8"))["stats"]["duration_ms"])
    except Exception:  # noqa: BLE001
        return None


async def _seed_showcase(db) -> None:
    """展示数据包：样片成片 + 能力快照 + 待审核工单（全部幂等）。"""
    student = (
        await db.execute(select(User).where(User.username == "student01"))
    ).scalar_one_or_none()
    enterprise = (
        await db.execute(select(User).where(User.role == "enterprise"))
    ).scalars().first()
    if student is None or enterprise is None:
        print("skip showcase（演示账号缺失）")
        return

    # 1) 五维能力快照（学生工作台首屏能力条有数据）
    has_ability = (
        await db.execute(
            select(AbilitySnapshot).where(AbilitySnapshot.student_id == student.id)
        )
    ).scalars().first()
    if has_ability is None:
        for dimension, score in ABILITY_DEMO:
            db.add(
                AbilitySnapshot(
                    student_id=student.id,
                    dimension=dimension,
                    score=score,
                    source="review",
                    ref_id=0,
                )
            )
        print("created showcase ability snapshots（五维）")

    # 2) 展示剧集：剧本 + 成片（样片视频进存储并落库）
    scenario = _pick_scenario()
    if scenario is not None:
        script_work = (
            await db.execute(select(Work).where(Work.title == SHOWCASE_SCRIPT_TITLE))
        ).scalar_one_or_none()
        if script_work is None:
            script_work = Work(
                owner_type="user",
                owner_id=student.id,
                title=SHOWCASE_SCRIPT_TITLE,
                type="script",
                status="ready",
                meta_json={
                    "genre": "逆袭",
                    "target_market": "北美",
                    "episodes": 1,
                    "note": "演示剧本：来自 scenarios/north-america-revenge 确定性场景包",
                },
                created_by=student.id,
            )
            db.add(script_work)
            await db.flush()
            print("created showcase script work")

        video_work = (
            await db.execute(select(Work).where(Work.title == SHOWCASE_VIDEO_TITLE))
        ).scalar_one_or_none()
        if video_work is None:
            video_work = Work(
                owner_type="user",
                owner_id=student.id,
                title=SHOWCASE_VIDEO_TITLE,
                type="video",
                status="ready",
                ai_declare_json={
                    "agents_used": ["script", "storyboard", "tts", "compose"],
                    "human_edit_ratio": 0.2,
                    "note": "样片由确定性演示流水线生成（scenarios 包），素材均为程序化/合成，无第三方版权",
                },
                created_by=student.id,
            )
            db.add(video_work)
            await db.flush()
            # 视频文件进本地存储 + 资产落库（键规范与 save_asset 一致）
            video_src = scenario / "final.mp4"
            storage_key = f"works/{video_work.id}/video/showcase_final.mp4"
            from app.services.storage.factory import get_storage

            get_storage().put(storage_key, video_src.read_bytes(), "video/mp4")
            db.add(
                WorkAsset(
                    work_id=video_work.id,
                    kind="video",
                    storage_key=storage_key,
                    mime="video/mp4",
                    size=video_src.stat().st_size,
                    duration_ms=_scenario_duration_ms(scenario),
                )
            )
            print(f"created showcase video work（{scenario.name} → {storage_key}）")

    # 3) 两张待审核工单（教师合规审核演示有米下锅）
    for title, budget, requirements in PENDING_ORDERS:
        exists = (
            await db.execute(select(WorkOrder).where(WorkOrder.title == title))
        ).scalar_one_or_none()
        if exists is None:
            db.add(
                WorkOrder(
                    enterprise_id=enterprise.id,
                    title=title,
                    requirements_json=requirements,
                    budget_cents=budget,
                    status="pending_review",
                    verify_note="演示数据：企业已提交，等待教师合规审核",
                )
            )
            print(f"created pending order: {title[:20]}…")


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
        await _seed_showcase(db)
        await db.commit()
    print("seed done")


if __name__ == "__main__":
    asyncio.run(seed())
