"""作品与资产 API（W3）+ Rubric 批改入口（W6）。"""
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from app.core.deps import CurrentUser, DbSession, require_role
from app.core.responses import ok
from app.models.work import WorkAsset
from app.schemas.task import ReviewIn, ReviewOut
from app.schemas.work import (
    AiDeclareIn,
    AssetOut,
    GenerateIn,
    PublishParamsIn,
    RevisionIn,
    TextAssetIn,
    WorkCreateIn,
    WorkOut,
)
from app.services import tasks as tasks_service
from app.services import works as works_service
from app.services.storage.factory import get_storage
from sqlalchemy import select


def _work_dict(work) -> dict:
    return WorkOut.model_validate(work).model_dump(mode="json")


def _asset_dict(asset) -> dict:
    data = AssetOut.model_validate(asset).model_dump(mode="json")
    data["url"] = get_storage().get_url(asset.storage_key)
    return data


router = APIRouter(prefix="/works", tags=["作品"])


@router.post("", summary="创建作品")
async def create(body: WorkCreateIn, user: CurrentUser, db: DbSession):
    work = await works_service.create_work(
        db, user, body.title, body.type, body.task_id
    )
    return ok(_work_dict(work), "创建成功")


@router.get("", summary="我的作品列表")
async def list_my(
    user: CurrentUser,
    db: DbSession,
    type: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    rows, total = await works_service.list_works(
        db, user, type_=type, page=page, page_size=page_size
    )
    return ok(
        {
            "items": [_work_dict(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/{work_id}", summary="作品详情（含资产与版本链）")
async def detail(work_id: int, user: CurrentUser, db: DbSession):
    work, assets, versions = await works_service.get_work_detail(
        db, user, work_id
    )
    return ok(
        {
            "work": _work_dict(work),
            "assets": [_asset_dict(asset) for asset in assets],
            "versions": [_work_dict(item) for item in versions],
        }
    )


@router.post("/{work_id}/generate", summary="生成 / 重生成作品产物")
async def generate_work(
    work_id: int, body: GenerateIn, user: CurrentUser, db: DbSession
):
    work, result = await works_service.generate(db, user, work_id, body)
    data = {"work": _work_dict(work)}
    if result.get("async"):
        data.update(
            {
                "session_id": result["session_id"],
                "async": True,
                "status": "running",
            }
        )
        return ok(data, "已入队，请轮询 /api/v1/agent-tasks/{session_id} 查看进度")
    data.update(
        {
            "session_id": result.get("session_id"),
            "result": result.get("result"),
        }
    )
    return ok(data, "生成成功")


@router.post("/{work_id}/assets", summary="上传文件资产")
async def upload_asset(
    work_id: int,
    user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
    kind: str = Form(...),
):
    data = await file.read()
    asset = await works_service.add_file_asset(
        db,
        user,
        work_id,
        kind,
        file.filename or "upload.bin",
        data,
        file.content_type,
    )
    return ok(
        {
            "id": asset.id,
            "kind": asset.kind,
            "storage_key": asset.storage_key,
            "url": get_storage().get_url(asset.storage_key),
        },
        "上传成功",
    )


@router.post("/{work_id}/text-assets", summary="登记文本资产")
async def upload_text_asset(
    work_id: int, body: TextAssetIn, user: CurrentUser, db: DbSession
):
    data = body.content.encode("utf-8")
    mime = {"json": "application/json"}.get(body.kind, "text/plain; charset=utf-8")
    asset = await works_service.add_file_asset(
        db,
        user,
        work_id,
        body.kind,
        body.filename or f"{body.kind}.txt",
        data,
        mime,
    )
    return ok(
        {
            "id": asset.id,
            "kind": asset.kind,
            "storage_key": asset.storage_key,
            "url": get_storage().get_url(asset.storage_key),
        },
        "登记成功",
    )


@router.post("/{work_id}/ai-declare", summary="提交 AI 使用声明")
async def ai_declare(
    work_id: int, body: AiDeclareIn, user: CurrentUser, db: DbSession
):
    work = await works_service.set_ai_declare(
        db, user, work_id, body.model_dump()
    )
    return ok(_work_dict(work), "声明已保存")


@router.get("/{work_id}/assets", summary="资产列表（含访问 URL）")
async def list_assets(work_id: int, user: CurrentUser, db: DbSession):
    work, assets, _ = await works_service.get_work_detail(db, user, work_id)
    return ok(
        {
            "work_id": work.id,
            "items": [_asset_dict(asset) for asset in assets],
        }
    )


@router.post(
    "/{work_id}/review",
    summary="教师 Rubric 批改（触发能力快照）",
    dependencies=[Depends(require_role("teacher", "admin"))],
)
async def review_work(
    work_id: int, body: ReviewIn, user: CurrentUser, db: DbSession
):
    data = await tasks_service.review_work(db, user, work_id, body)
    review = data["review"]
    return ok(
        {
            "review": ReviewOut.model_validate(review).model_dump(mode="json"),
            "total": data["total"],
            "passed": data["passed"],
        },
        "批改完成",
    )


@router.post("/{work_id}/publish-params", summary="生成发布参数包（成片作品）")
async def create_publish_params(
    work_id: int, body: PublishParamsIn, user: CurrentUser, db: DbSession
):
    work, result = await works_service.generate_publish_params(db, user, work_id, body)
    return ok(
        {
            "work_id": work.id,
            "session_id": result.get("session_id"),
            "result": result.get("result"),
        },
        "发布参数已生成",
    )


@router.post("/{work_id}/revision", summary="提交人工修订产物（自动比对差异度）")
async def submit_revision(
    work_id: int, body: RevisionIn, user: CurrentUser, db: DbSession
):
    data = await works_service.submit_revision(db, user, work_id, body)
    return ok(data, "修订已保存，已自动计算与 AI 原版的差异度")


@router.get("/{work_id}/review", summary="查看批改结果")
async def get_review(work_id: int, user: CurrentUser, db: DbSession):
    data = await tasks_service.get_work_review(db, user, work_id)
    return ok(
        {
            "work_id": data["work_id"],
            "latest": ReviewOut.model_validate(data["latest"]).model_dump(mode="json")
            if data["latest"]
            else None,
            "history": [
                ReviewOut.model_validate(item).model_dump(mode="json")
                for item in data["history"]
            ],
        }
    )
