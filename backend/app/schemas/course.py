"""课程相关入参出参。"""
from pydantic import BaseModel, Field


class CourseCreateIn(BaseModel):
    """管理员创建课程（可附带班级名）。"""

    code: str = Field(min_length=2, max_length=50, description="课程代码，如 EB2026")
    name: str = Field(min_length=1, max_length=100)
    semester: str | None = Field(default=None, max_length=20, description="如 2026-2027-1")
    teacher_id: int | None = Field(default=None, description="授课教师 user_id")
    class_names: list[str] = Field(
        default_factory=list, description="班级名列表（可选），如 ['电商2301班']"
    )
