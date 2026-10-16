"""实训任务 API（W6）：发布 / 列表 / 详情 / 提交 / 截止 / 提交列表。"""
from fastapi import APIRouter, Depends

from app.core.deps import CurrentUser, DbSession, require_role
from app.core.responses import ok
from app.schemas.task import SubmitIn, TaskCreateIn, TaskOut
from app.services import tasks as tasks_service

router = APIRouter(prefix="/tasks", tags=["实训任务"])


def _task_dict(task) -> dict:
    return TaskOut.model_validate(task).model_dump(mode="json")


def _submission_dict(item: dict) -> dict:
    data = dict(item)
    data["submitted_at"] = (
        data["submitted_at"].isoformat() if data.get("submitted_at") else None
    )
    return data


@router.get("", summary="任务列表（学生：可接；教师：我发布的）")
async def list_tasks(user: CurrentUser, db: DbSession):
    rows = await tasks_service.list_tasks(db, user)
    return ok({"items": [_task_dict(row) for row in rows], "total": len(rows)})


@router.post(
    "",
    summary="教师发布任务",
    dependencies=[Depends(require_role("teacher", "admin"))],
)
async def create_task(body: TaskCreateIn, user: CurrentUser, db: DbSession):
    task = await tasks_service.create_task(db, user, body)
    return ok(_task_dict(task), "任务已发布" if task.status == "published" else "草稿已保存")


@router.get("/{task_id}", summary="任务详情 + Rubric")
async def get_task(task_id: int, user: CurrentUser, db: DbSession):
    detail = await tasks_service.get_task_detail(db, user, task_id)
    data = {
        "task": _task_dict(detail["task"]),
        "submissions_count": detail["submissions_count"],
        "my_submission": None,
    }
    if detail["my_submission"] is not None:
        submission = detail["my_submission"]
        data["my_submission"] = {
            "id": submission.id,
            "work_ids": submission.work_ids_json or [],
            "status": submission.status,
            "note": submission.note,
            "submitted_at": submission.submitted_at.isoformat()
            if submission.submitted_at
            else None,
        }
    return ok(data)


@router.post("/{task_id}/submit", summary="学生提交交付物")
async def submit_task(
    task_id: int, body: SubmitIn, user: CurrentUser, db: DbSession
):
    submission = await tasks_service.submit_task(
        db, user, task_id, body.work_ids, body.note
    )
    return ok(
        {
            "id": submission.id,
            "task_id": submission.task_id,
            "status": submission.status,
            "work_ids": submission.work_ids_json,
            "submitted_at": submission.submitted_at.isoformat()
            if submission.submitted_at
            else None,
        },
        "提交成功",
    )


@router.post(
    "/{task_id}/close",
    summary="教师截止任务",
    dependencies=[Depends(require_role("teacher", "admin"))],
)
async def close_task(task_id: int, user: CurrentUser, db: DbSession):
    task = await tasks_service.close_task(db, user, task_id)
    return ok(_task_dict(task), "任务已截止")


@router.get(
    "/{task_id}/submissions",
    summary="提交列表（教师视角）",
    dependencies=[Depends(require_role("teacher", "admin"))],
)
async def list_submissions(task_id: int, user: CurrentUser, db: DbSession):
    items = await tasks_service.list_submissions(db, user, task_id)
    return ok({"items": [_submission_dict(item) for item in items], "total": len(items)})
