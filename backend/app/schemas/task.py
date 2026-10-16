"""实训任务与能力图谱入参出参（W6）。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RubricCriterion(BaseModel):
    key: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=50)
    dimension: str = Field(description="五维能力维度之一")
    # 允许填任意正权重（如 3:1），服务层自动归一化到合计 1.0
    weight: float = Field(gt=0, le=100)
    description: str | None = None


class Rubric(BaseModel):
    criteria: list[RubricCriterion] = Field(min_length=1, max_length=10)
    pass_score: float = Field(default=60, ge=0, le=100)


class TaskCreateIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    brief: str | None = None
    course_id: int | None = None
    deadline: datetime | None = None
    team_rule: str = Field(default="free", pattern="^(free|cross_major|forced)$")
    deliverable_json: dict | None = None
    rubric: Rubric | None = None
    publish: bool = True


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    brief: str | None = None
    course_id: int | None = None
    rubric_json: dict | None = None
    team_rule: str
    deliverable_json: dict | None = None
    deadline: datetime | None = None
    status: str
    creator_id: int
    created_at: datetime | None = None


class SubmitIn(BaseModel):
    work_ids: list[int] = Field(min_length=1, max_length=10)
    note: str | None = Field(default=None, max_length=500)


class SubmissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    submitter_id: int
    work_ids_json: list | None = None
    note: str | None = None
    status: str
    submitted_at: datetime | None = None


class CriterionScore(BaseModel):
    key: str
    score: float = Field(ge=0, le=100)


class ReviewIn(BaseModel):
    criterion_scores: list[CriterionScore] = Field(min_length=1, max_length=10)
    comment: str | None = Field(default=None, max_length=2000)


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    work_id: int
    teacher_id: int
    rubric_score_json: dict | None = None
    comment: str | None = None
    ai_diff_ratio: float | None = None
    created_at: datetime | None = None


class AbilityPoint(BaseModel):
    dimension: str
    score: float
    source: str
    created_at: datetime | None = None


class AbilityOut(BaseModel):
    student_id: int
    latest: dict[str, float] = Field(default_factory=dict)
    history: list[AbilityPoint] = Field(default_factory=list)
    review_count: int = 0


class ClassAbilityOut(BaseModel):
    class_id: int
    student_count: int
    averages: dict[str, float] = Field(default_factory=dict)
