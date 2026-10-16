"""实训任务服务：发布 / 提交 / Rubric 批改 / 能力快照（W6）。

能力分规则：批改时按 Rubric 分项得分逐维落 ability_snapshots（只追加），
并把「各维最新分」缓存到 StudentProfile.ability_json 供列表页快速展示。
"""
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profile import StudentProfile
from app.models.review import ABILITY_DIMENSIONS, AbilitySnapshot, WorkReview
from app.models.task import TaskSubmission, TrainingTask
from app.models.user import User
from app.models.work import Work
from app.schemas.task import ReviewIn, TaskCreateIn
from app.services.ability import latest_scores_by_dimension

# 默认 Rubric：五项对应五维能力，权重合计 1.0
DEFAULT_RUBRIC = {
    "criteria": [
        {
            "key": "content_creation",
            "name": "剧本与内容质量",
            "dimension": "内容创作",
            "weight": 0.25,
            "description": "故事结构、钩子设计、台词质量",
        },
        {
            "key": "cross_culture",
            "name": "跨文化本地化",
            "dimension": "跨文化沟通",
            "weight": 0.20,
            "description": "目标市场文化适配与表达",
        },
        {
            "key": "ecommerce",
            "name": "发布与运营设计",
            "dimension": "电商运营",
            "weight": 0.20,
            "description": "发布参数、标签与投放思路",
        },
        {
            "key": "ai_tools",
            "name": "AI 工具运用",
            "dimension": "AI工具应用",
            "weight": 0.20,
            "description": "智能体使用策略与提效程度",
        },
        {
            "key": "analytics",
            "name": "数据与复盘",
            "dimension": "数据分析",
            "weight": 0.15,
            "description": "数据意识与复盘改进",
        },
    ],
    "pass_score": 60,
}


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=422, detail={"code": 40001, "message": message})


def _conflict(message: str) -> HTTPException:
    return HTTPException(status_code=409, detail={"code": 40901, "message": message})


def _forbidden(message: str = "无权限执行该操作") -> HTTPException:
    return HTTPException(status_code=403, detail={"code": 40301, "message": message})


def _not_found(message: str = "资源不存在") -> HTTPException:
    return HTTPException(status_code=404, detail={"code": 40401, "message": message})


def _validate_rubric(rubric: dict) -> dict:
    criteria = rubric.get("criteria") or []
    if not criteria:
        raise _bad_request("Rubric 至少需要一个评分项")
    keys = set()
    for item in criteria:
        if item.get("dimension") not in ABILITY_DIMENSIONS:
            raise _bad_request(
                f"评分项维度必须是五维之一：{'/'.join(ABILITY_DIMENSIONS)}"
            )
        if item.get("key") in keys:
            raise _bad_request(f"评分项 key 重复：{item.get('key')}")
        keys.add(item.get("key"))
    total_weight = sum(float(item.get("weight", 0)) for item in criteria)
    if total_weight <= 0:
        raise _bad_request("Rubric 权重之和必须大于 0")
    # 权重归一化，避免教师填写不规范
    for item in criteria:
        item["weight"] = round(float(item["weight"]) / total_weight, 4)
    rubric["criteria"] = criteria
    rubric.setdefault("pass_score", 60)
    return rubric


# ---------- 任务 ----------


async def create_task(
    db: AsyncSession, user: User, body: TaskCreateIn
) -> TrainingTask:
    rubric = (
        _validate_rubric(body.rubric.model_dump())
        if body.rubric
        else DEFAULT_RUBRIC
    )
    task = TrainingTask(
        course_id=body.course_id,
        title=body.title,
        brief=body.brief,
        rubric_json=rubric,
        team_rule=body.team_rule,
        deliverable_json=body.deliverable_json,
        deadline=body.deadline,
        status="published" if body.publish else "draft",
        creator_id=user.id,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def list_tasks(db: AsyncSession, user: User) -> list[TrainingTask]:
    stmt = select(TrainingTask)
    if user.role == "teacher":
        stmt = stmt.where(TrainingTask.creator_id == user.id)
    elif user.role == "student":
        stmt = stmt.where(TrainingTask.status == "published")
    # admin 看全部
    stmt = stmt.order_by(TrainingTask.id.desc())
    return list((await db.execute(stmt)).scalars().all())


async def _load_task(db: AsyncSession, task_id: int) -> TrainingTask:
    task = (
        await db.execute(select(TrainingTask).where(TrainingTask.id == task_id))
    ).scalar_one_or_none()
    if task is None:
        raise _not_found("任务不存在")
    return task


def _require_task_owner(task: TrainingTask, user: User) -> None:
    if user.role != "admin" and task.creator_id != user.id:
        raise _forbidden("只有任务发布教师可以执行该操作")


async def get_task_detail(db: AsyncSession, user: User, task_id: int) -> dict:
    task = await _load_task(db, task_id)
    result: dict = {"task": task, "submissions_count": None, "my_submission": None}
    if user.role in ("teacher", "admin"):
        result["submissions_count"] = (
            await db.execute(
                select(func.count())
                .select_from(TaskSubmission)
                .where(TaskSubmission.task_id == task_id)
            )
        ).scalar_one()
    if user.role == "student":
        result["my_submission"] = (
            await db.execute(
                select(TaskSubmission).where(
                    TaskSubmission.task_id == task_id,
                    TaskSubmission.submitter_id == user.id,
                )
            )
        ).scalar_one_or_none()
    return result


async def close_task(db: AsyncSession, user: User, task_id: int) -> TrainingTask:
    task = await _load_task(db, task_id)
    _require_task_owner(task, user)
    task.status = "closed"
    await db.commit()
    await db.refresh(task)
    return task


# ---------- 提交 ----------


async def submit_task(
    db: AsyncSession, user: User, task_id: int, work_ids: list[int], note: str | None
) -> TaskSubmission:
    if user.role != "student":
        raise _forbidden("只有学生可以提交任务")
    task = await _load_task(db, task_id)
    if task.status != "published":
        raise _conflict("任务未发布或已截止，无法提交")
    if task.deadline is not None:
        now = (
            datetime.now(task.deadline.tzinfo)
            if task.deadline.tzinfo
            else datetime.now()
        )
        if task.deadline < now:
            raise _conflict("任务已过截止时间")

    exists = (
        await db.execute(
            select(TaskSubmission).where(
                TaskSubmission.task_id == task_id,
                TaskSubmission.submitter_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if exists is not None:
        raise _conflict("你已提交过该任务；如需重新提交请联系教师退回")

    works = (
        (
            await db.execute(
                select(Work).where(
                    Work.id.in_(work_ids), Work.created_by == user.id
                )
            )
        )
        .scalars()
        .all()
    )
    found_ids = {work.id for work in works}
    missing = [wid for wid in work_ids if wid not in found_ids]
    if missing:
        raise _bad_request(f"作品不存在或不属于你：{missing}")

    for work in works:
        work.task_id = task.id

    submission = TaskSubmission(
        task_id=task.id,
        submitter_id=user.id,
        work_ids_json=list(work_ids),
        note=note,
        status="submitted",
    )
    db.add(submission)
    await db.commit()
    await db.refresh(submission)
    return submission


async def list_submissions(
    db: AsyncSession, user: User, task_id: int
) -> list[dict]:
    task = await _load_task(db, task_id)
    _require_task_owner(task, user)
    rows = (
        (
            await db.execute(
                select(TaskSubmission)
                .where(TaskSubmission.task_id == task_id)
                .order_by(TaskSubmission.id.desc())
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return []

    # 批量取学生 / 作品 / 批改数（三条查询，无 N+1）
    submitter_ids = {s.submitter_id for s in rows}
    users = (
        (
            await db.execute(select(User).where(User.id.in_(submitter_ids)))
        )
        .scalars()
        .all()
    )
    name_map = {u.id: u.username for u in users}

    all_work_ids = {wid for s in rows for wid in (s.work_ids_json or [])}
    works = (
        (
            await db.execute(select(Work).where(Work.id.in_(all_work_ids)))
        )
        .scalars()
        .all()
        if all_work_ids
        else []
    )
    work_map = {w.id: w for w in works}

    reviewed_map: dict[int, int] = {}
    if all_work_ids:
        reviewed_rows = (
            await db.execute(
                select(WorkReview.work_id, func.count())
                .where(WorkReview.work_id.in_(all_work_ids))
                .group_by(WorkReview.work_id)
            )
        ).all()
        reviewed_map = {work_id: count for work_id, count in reviewed_rows}

    items = []
    for submission in rows:
        work_ids = submission.work_ids_json or []
        items.append(
            {
                "id": submission.id,
                "task_id": submission.task_id,
                "submitter_id": submission.submitter_id,
                "submitter_name": name_map.get(submission.submitter_id, ""),
                "work_ids": work_ids,
                "works": [
                    {
                        "id": work_map[wid].id,
                        "title": work_map[wid].title,
                        "type": work_map[wid].type,
                        "status": work_map[wid].status,
                    }
                    for wid in work_ids
                    if wid in work_map
                ],
                "note": submission.note,
                "status": submission.status,
                "reviewed_works": sum(reviewed_map.get(wid, 0) for wid in work_ids),
                "submitted_at": submission.submitted_at,
            }
        )
    return items


# ---------- 批改与能力快照 ----------


async def _resolve_rubric(db: AsyncSession, work: Work) -> dict:
    if work.task_id is not None:
        task = (
            await db.execute(
                select(TrainingTask).where(TrainingTask.id == work.task_id)
            )
        ).scalar_one_or_none()
        if task is not None and task.rubric_json:
            return task.rubric_json
    return DEFAULT_RUBRIC


def _require_review_permission(work: Work, task: TrainingTask | None, user: User) -> None:
    if user.role == "admin":
        return
    if user.role != "teacher":
        raise _forbidden("只有教师可以批改")
    if task is not None and task.creator_id != user.id:
        raise _forbidden("只有任务发布教师可以批改该任务的作品")


async def review_work(
    db: AsyncSession, user: User, work_id: int, body: ReviewIn
) -> dict:
    work = (
        await db.execute(select(Work).where(Work.id == work_id))
    ).scalar_one_or_none()
    if work is None:
        raise _not_found("作品不存在")

    task = None
    if work.task_id is not None:
        task = (
            await db.execute(
                select(TrainingTask).where(TrainingTask.id == work.task_id)
            )
        ).scalar_one_or_none()
    _require_review_permission(work, task, user)

    rubric = await _resolve_rubric(db, work)
    criterion_map = {item["key"]: item for item in rubric["criteria"]}
    scores = {}
    for item in body.criterion_scores:
        if item.key not in criterion_map:
            raise _bad_request(f"评分项不在 Rubric 中：{item.key}")
        scores[item.key] = float(item.score)
    missing = [key for key in criterion_map if key not in scores]
    if missing:
        raise _bad_request(f"缺少评分项：{missing}")

    total = sum(scores[key] * float(criterion_map[key]["weight"]) for key in scores)
    detail_scores = {
        key: {
            "name": criterion_map[key]["name"],
            "dimension": criterion_map[key]["dimension"],
            "weight": float(criterion_map[key]["weight"]),
            "score": scores[key],
        }
        for key in scores
    }

    declare = work.ai_declare_json or {}
    # 优先实测修改度（学生提交过人工修订产物时系统自动计算），自报值兜底
    measured = declare.get("measured_edit_ratio")
    declared = declare.get("human_edit_ratio")
    ai_diff_ratio = measured if measured is not None else declared
    edit_ratio_source = (
        "measured" if measured is not None else ("declared" if declared is not None else None)
    )

    review = WorkReview(
        work_id=work.id,
        teacher_id=user.id,
        rubric_score_json={
            "total": round(total, 2),
            "pass_score": rubric.get("pass_score", 60),
            "passed": total >= float(rubric.get("pass_score", 60)),
            "items": detail_scores,
            "edit_ratio_source": edit_ratio_source,
        },
        comment=body.comment,
        ai_diff_ratio=ai_diff_ratio,
    )
    db.add(review)
    await db.flush()

    # 逐维能力快照（只追加）；同一维度多次评分取最新为该维当前分
    student_id = work.created_by
    for key, item in detail_scores.items():
        db.add(
            AbilitySnapshot(
                student_id=student_id,
                dimension=item["dimension"],
                score=item["score"],
                source="review",
                ref_id=review.id,
            )
        )
    await _refresh_ability_cache(db, student_id)

    # 提交状态推进
    if task is not None:
        submission = (
            await db.execute(
                select(TaskSubmission).where(
                    TaskSubmission.task_id == task.id,
                    TaskSubmission.submitter_id == student_id,
                )
            )
        ).scalar_one_or_none()
        if submission is not None:
            submission.status = "reviewed"

    await db.commit()
    await db.refresh(review)
    return {
        "review": review,
        "total": round(total, 2),
        "passed": total >= float(rubric.get("pass_score", 60)),
    }


async def _refresh_ability_cache(db: AsyncSession, student_id: int) -> None:
    profile = (
        await db.execute(
            select(StudentProfile).where(StudentProfile.user_id == student_id)
        )
    ).scalar_one_or_none()
    if profile is None:
        return
    # 单查询取「每维最新分」（原为每维一次查询）
    profile.ability_json = await latest_scores_by_dimension(db, student_id)


async def get_work_review(db: AsyncSession, user: User, work_id: int) -> dict:
    work = (
        await db.execute(select(Work).where(Work.id == work_id))
    ).scalar_one_or_none()
    if work is None:
        raise _not_found("作品不存在")
    if (
        user.role not in ("teacher", "admin")
        and work.created_by != user.id
    ):
        raise _forbidden("无权查看该作品的批改")
    reviews = (
        (
            await db.execute(
                select(WorkReview)
                .where(WorkReview.work_id == work_id)
                .order_by(WorkReview.id.desc())
            )
        )
        .scalars()
        .all()
    )
    return {
        "work_id": work_id,
        "latest": reviews[0] if reviews else None,
        "history": list(reviews),
    }
