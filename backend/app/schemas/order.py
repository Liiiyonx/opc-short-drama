"""工单入参出参（W7）。金额一律用分（bigint）。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OrderCreateIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    requirements: dict | None = Field(
        default=None,
        description="题材/市场/集数/语言/交付要求（结构化）",
    )
    budget_cents: int = Field(default=0, ge=0, description="预算（分）")
    deadline: datetime | None = None
    submit: bool = Field(default=True, description="true 直接提交审核，false 存草稿")


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    enterprise_id: int
    title: str
    requirements_json: dict | None = None
    budget_cents: int
    deadline: datetime | None = None
    status: str
    verify_note: str | None = None
    created_at: datetime | None = None


class OrderVerifyIn(BaseModel):
    approved: bool
    note: str | None = Field(default=None, max_length=500)


class BidIn(BaseModel):
    amount_cents: int = Field(gt=0, description="报价（分）")
    proposal: str | None = Field(default=None, max_length=2000)


class BidOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    bidder_id: int
    amount_cents: int
    proposal: str | None = None
    status: str
    created_at: datetime | None = None


class AwardIn(BaseModel):
    bid_id: int
