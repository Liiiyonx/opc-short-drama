"""管理后台测试（2026-10-16）：用户管理 + 课程创建 + 权限边界。"""
import os

os.environ["LLM_PROVIDER"] = "mock"
os.environ["TTS_PROVIDER"] = "mock"

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
from app.api.v1 import courses as courses_api
from app.api.v1 import users as users_api
from app.core.config import get_settings
from app.core.security import hash_password
from app.db.base import Base
from app.models.course import Course, CourseClass
from app.models.user import User
from app.schemas.course import CourseCreateIn
from app.schemas.user import UserCreate, UserStatusIn


@pytest.fixture
async def db(tmp_path, monkeypatch):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path}/test.db", poolclass=NullPool
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path / "storage"))
    get_settings.cache_clear()
    async with factory() as session:
        admin = User(
            username="adm_root",
            password_hash=hash_password("test123456"),
            role="admin",
            status=1,
        )
        session.add(admin)
        await session.commit()
        await session.refresh(admin)
        yield session, admin
    get_settings.cache_clear()
    await engine.dispose()


async def test_admin_creates_and_toggles_user(db):
    session, admin = db
    created = await users_api.create_user(
        UserCreate(username="new_stu", password="pass123456", role="student"),
        db=session,
    )
    assert created["data"]["role"] == "student"
    assert created["data"]["status"] == 1

    disabled = await users_api.update_user_status(
        created["data"]["id"], UserStatusIn(status=0), db=session
    )
    assert disabled["data"]["status"] == 0

    # 重名冲突
    with pytest.raises(HTTPException) as exc:
        await users_api.create_user(
            UserCreate(username="new_stu", password="pass123456", role="student"),
            db=session,
        )
    assert exc.value.status_code == 409

    # 不存在用户
    with pytest.raises(HTTPException) as exc2:
        await users_api.update_user_status(99999, UserStatusIn(status=1), db=session)
    assert exc2.value.status_code == 404


async def test_admin_creates_course_with_classes(db):
    session, admin = db
    result = await courses_api.create_course(
        CourseCreateIn(
            code="EB2026",
            name="电子商务出海实战",
            semester="2026-2027-1",
            class_names=["电商2301班", "商务英语2302班"],
        ),
        db=session,
    )
    assert result["data"]["code"] == "EB2026"
    courses = (
        (await session.execute(select(Course).where(Course.code == "EB2026")))
        .scalars()
        .all()
    )
    assert len(courses) == 1
    classes = (
        (
            await session.execute(
                select(CourseClass).where(CourseClass.course_id == courses[0].id)
            )
        )
        .scalars()
        .all()
    )
    assert len(classes) == 2

    # 重复课程代码
    with pytest.raises(HTTPException) as exc:
        await courses_api.create_course(
            CourseCreateIn(code="EB2026", name="重复"), db=session
        )
    assert exc.value.status_code == 409


async def test_course_list_visible_to_all_roles(db):
    session, admin = db
    await courses_api.create_course(
        CourseCreateIn(code="X1", name="测试课"), db=session
    )
    student = User(
        username="stu_course",
        password_hash=hash_password("test123456"),
        role="student",
        status=1,
    )
    session.add(student)
    await session.commit()
    listed = await courses_api.list_courses(user=student, db=session)
    assert listed["data"]["total"] >= 1
