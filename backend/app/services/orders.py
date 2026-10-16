"""工单服务：发布 / 审核 / 大厅 / 投标 / 定标（W7）。

合规要点（docs/01 §2.2）：不做支付托管，平台只存交易凭证；
企业需 verify_status=approved；投标需五维能力均分达阈值（默认 60）。
"""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import OrderBid, WorkOrder
from app.models.profile import EnterpriseProfile
from app.models.user import User
from app.schemas.order import OrderCreateIn
from app.services.ability import latest_scores_by_dimension

ABILITY_BID_THRESHOLD = 60.0


def _forbidden(message: str = "无权限执行该操作") -> HTTPException:
    return HTTPException(status_code=403, detail={"code": 40301, "message": message})


def _not_found(message: str = "工单不存在") -> HTTPException:
    return HTTPException(status_code=404, detail={"code": 40401, "message": message})


def _conflict(message: str) -> HTTPException:
    return HTTPException(status_code=409, detail={"code": 40901, "message": message})


async def _ability_average(db: AsyncSession, student_id: int) -> float | None:
    """五维最新分均值；无任何评分数据返回 None（单查询，无 5×N）。"""
    latest = await latest_scores_by_dimension(db, student_id)
    if not latest:
        return None
    return round(sum(latest.values()) / len(latest), 2)


async def create_order(
    db: AsyncSession, user: User, body: OrderCreateIn
) -> WorkOrder:
    if user.role != "enterprise":
        raise _forbidden("只有企业账号可以发布工单")
    profile = (
        await db.execute(
            select(EnterpriseProfile).where(EnterpriseProfile.user_id == user.id)
        )
    ).scalar_one_or_none()
    if profile is None or profile.verify_status != "approved":
        raise _forbidden("企业资质未审核通过，暂不能发布工单")

    order = WorkOrder(
        enterprise_id=user.id,
        title=body.title,
        requirements_json=body.requirements,
        budget_cents=body.budget_cents,
        deadline=body.deadline,
        status="pending_review" if body.submit else "draft",
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order


async def list_orders(db: AsyncSession, user: User) -> list[WorkOrder]:
    stmt = select(WorkOrder)
    if user.role == "student":
        stmt = stmt.where(WorkOrder.status.in_(["published", "bidding"]))
    elif user.role == "enterprise":
        stmt = stmt.where(WorkOrder.enterprise_id == user.id)
    elif user.role == "teacher":
        pass  # 教师可见全部（审核 + 教学适配观察）
    stmt = stmt.order_by(WorkOrder.id.desc())
    return list((await db.execute(stmt)).scalars().all())


async def _load_order(db: AsyncSession, order_id: int) -> WorkOrder:
    order = (
        await db.execute(select(WorkOrder).where(WorkOrder.id == order_id))
    ).scalar_one_or_none()
    if order is None:
        raise _not_found()
    return order


def _require_owner(order: WorkOrder, user: User) -> None:
    if user.role != "admin" and order.enterprise_id != user.id:
        raise _forbidden("只有工单发布企业可以执行该操作")


async def get_order_detail(db: AsyncSession, user: User, order_id: int) -> dict:
    order = await _load_order(db, order_id)
    bids_stmt = select(OrderBid).where(OrderBid.order_id == order_id)
    if user.role == "student":
        bids_stmt = bids_stmt.where(OrderBid.bidder_id == user.id)
    elif user.role not in ("enterprise", "teacher", "admin"):
        bids_stmt = bids_stmt.where(OrderBid.bidder_id == user.id)
    elif user.role == "enterprise":
        _require_owner(order, user)
    bids = list(
        (await db.execute(bids_stmt.order_by(OrderBid.id))).scalars().all()
    )
    bidder_names = {}
    if bids:
        users = (
            (
                await db.execute(
                    select(User).where(User.id.in_([b.bidder_id for b in bids]))
                )
            )
            .scalars()
            .all()
        )
        for u in users:
            bidder_names[u.id] = u.username
    return {
        "order": order,
        "bids": [
            {
                "id": bid.id,
                "order_id": bid.order_id,
                "bidder_id": bid.bidder_id,
                "bidder_name": bidder_names.get(bid.bidder_id, ""),
                "amount_cents": bid.amount_cents,
                "proposal": bid.proposal,
                "status": bid.status,
                "created_at": bid.created_at,
            }
            for bid in bids
        ],
    }


async def verify_order(
    db: AsyncSession, user: User, order_id: int, approved: bool, note: str | None
) -> WorkOrder:
    if user.role not in ("teacher", "admin"):
        raise _forbidden("只有教师或管理员可以审核工单")
    order = await _load_order(db, order_id)
    if order.status not in ("pending_review", "draft"):
        raise _conflict(f"当前状态（{order.status}）不可审核")
    if approved:
        order.status = "published"
        order.verify_note = note or "审核通过"
    else:
        order.status = "draft"
        order.verify_note = note or "请修改后重新提交"
    await db.commit()
    await db.refresh(order)
    return order


async def bid_order(
    db: AsyncSession,
    user: User,
    order_id: int,
    amount_cents: int,
    proposal: str | None,
) -> tuple[OrderBid, float | None]:
    if user.role != "student":
        raise _forbidden("只有学生可以投标")
    order = await _load_order(db, order_id)
    if order.status not in ("published", "bidding"):
        raise _conflict("工单当前不在可投标状态")

    average = await _ability_average(db, user.id)
    if average is not None and average < ABILITY_BID_THRESHOLD:
        raise _forbidden(
            f"五维能力均分 {average} 分，未达投标门槛 {ABILITY_BID_THRESHOLD:.0f} 分"
        )

    exists = (
        await db.execute(
            select(OrderBid).where(
                OrderBid.order_id == order_id, OrderBid.bidder_id == user.id
            )
        )
    ).scalar_one_or_none()
    if exists is not None:
        raise _conflict("你已投标该工单，如需修改请联系企业方")

    bid = OrderBid(
        order_id=order_id,
        bidder_id=user.id,
        amount_cents=amount_cents,
        proposal=proposal,
    )
    db.add(bid)
    if order.status == "published":
        order.status = "bidding"
    await db.commit()
    await db.refresh(bid)
    return bid, average


async def list_bids(db: AsyncSession, user: User, order_id: int) -> list[dict]:
    order = await _load_order(db, order_id)
    if user.role not in ("teacher", "admin"):
        _require_owner(order, user)
    data = await get_order_detail(db, user, order_id)
    return data["bids"]


async def award_order(
    db: AsyncSession, user: User, order_id: int, bid_id: int
) -> tuple[WorkOrder, OrderBid]:
    order = await _load_order(db, order_id)
    _require_owner(order, user)
    if order.status != "bidding":
        raise _conflict("工单不在评标状态")
    bid = (
        await db.execute(
            select(OrderBid).where(OrderBid.id == bid_id, OrderBid.order_id == order_id)
        )
    ).scalar_one_or_none()
    if bid is None or bid.status != "active":
        raise _not_found("投标记录不存在或已失效")

    all_bids = (
        (await db.execute(select(OrderBid).where(OrderBid.order_id == order_id)))
        .scalars()
        .all()
    )
    for item in all_bids:
        item.status = "won" if item.id == bid.id else "lost"
    order.status = "awarded"
    await db.commit()
    await db.refresh(order)
    await db.refresh(bid)
    return order, bid
