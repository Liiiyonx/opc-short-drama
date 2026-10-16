"""模型汇总：Alembic autogenerate 依赖本包导入全部模型。"""
from app.models.agent import AgentCallLog, AgentSession  # noqa: F401
from app.models.course import Course, CourseClass  # noqa: F401
from app.models.profile import (  # noqa: F401
    EnterpriseProfile,
    StudentProfile,
    TeacherProfile,
)
from app.models.user import User  # noqa: F401
from app.models.work import Work, WorkAsset  # noqa: F401
