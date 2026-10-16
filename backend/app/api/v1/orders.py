"""工单 API（W7）：发布 / 大厅 / 详情 / 审核 / 投标 / 定标。"""
from fastapi import APIRouter

from app.core.deps import CurrentUser, DbSession
from app.core.responses import ok
from app.schemas.order import (
    AwardIn,
    BidIn,
    BidOut,
    OrderCreateIn,
    OrderOut,
    OrderVerifyIn,
)
from app.services import orders as orders_service

router = APIRouter(prefix="/orders", tags=["工单"])


def _order_dict(order) -> dict:
    return OrderOut.model_validate(order).model_dump(mode="json")


def _bid_dict(bid: dict) -> dict:
    data = dict(bid)
    if data.get("created_at") is not None:
        data["created_at"] = data["created_at"].isoformat()
    return data


@router.post("", summary="企业发布工单")
async def create_order(body: OrderCreateIn, user: CurrentUser, db: DbSession):
    order = await orders_service.create_order(db, user, body)
    return ok(
        _order_dict(order),
        "已提交审核" if order.status == "pending_review" else "草稿已保存",
    )


@router.get("", summary="工单列表（学生：大厅；企业：我的；教师：全部）")
async def list_orders(user: CurrentUser, db: DbSession):
    rows = await orders_service.list_orders(db, user)
    return ok({"items": [_order_dict(row) for row in rows], "total": len(rows)})


@router.get("/{order_id}", summary="工单详情（含投标）")
async def get_order(order_id: int, user: CurrentUser, db: DbSession):
    data = await orders_service.get_order_detail(db, user, order_id)
    return ok(
        {
            "order": _order_dict(data["order"]),
            "bids": [_bid_dict(item) for item in data["bids"]],
        }
    )


@router.post("/{order_id}/verify", summary="教师/管理员审核工单")
async def verify_order(
    order_id: int, body: OrderVerifyIn, user: CurrentUser, db: DbSession
):
    order = await orders_service.verify_order(
        db, user, order_id, body.approved, body.note
    )
    return ok(_order_dict(order), "审核完成")


@router.post("/{order_id}/bid", summary="学生投标")
async def bid_order(order_id: int, body: BidIn, user: CurrentUser, db: DbSession):
    bid, average = await orders_service.bid_order(
        db, user, order_id, body.amount_cents, body.proposal
    )
    return ok(
        {
            "bid": BidOut.model_validate(bid).model_dump(mode="json"),
            "ability_average": average,
        },
        "投标成功",
    )


@router.get("/{order_id}/bids", summary="投标列表（企业/教师视角）")
async def list_bids(order_id: int, user: CurrentUser, db: DbSession):
    bids = await orders_service.list_bids(db, user, order_id)
    return ok({"items": [_bid_dict(item) for item in bids], "total": len(bids)})


@router.post("/{order_id}/award", summary="企业定标")
async def award_order(order_id: int, body: AwardIn, user: CurrentUser, db: DbSession):
    order, bid = await orders_service.award_order(db, user, order_id, body.bid_id)
    return ok(
        {
            "order": _order_dict(order),
            "winning_bid": BidOut.model_validate(bid).model_dump(mode="json"),
        },
        "定标完成（P0 线下结算，平台仅存凭证）",
    )
