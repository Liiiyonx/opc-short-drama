"""人才匹配 Agent（match）：企业工单需求 → 学生候选人脱敏排行。

契约（docs/05 §3.8，P1 补齐）：规则化打分（透明可解释，非黑箱）——
五维最新分均值为主分，按工单需求侧重维度加权；输出脱敏视图（隐藏用户名/学号），
意向确认后由教师/管理员协助建立联系。
"""
from pydantic import BaseModel, Field
from fastapi import HTTPException

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import Agent, AgentContext
from app.models.order import WorkOrder
from app.models.profile import StudentProfile
from app.models.user import User
from app.services.ability import latest_scores_by_students

# 工单字段 → 侧重能力维度（可解释权重：主分 70% + 侧重维度 30%）
FOCUS_DIMENSIONS = {
    "genre": "内容创作",
    "market": "跨文化沟通",
    "lang": "跨文化沟通",
    "delivery": "电商运营",
}
DIMENSION_LABELS = ["内容创作", "跨文化沟通", "电商运营", "AI工具应用", "数据分析"]


class MatchInput(BaseModel):
    order_id: int
    top_n: int = Field(default=5, ge=1, le=20)


class MatchCandidate(BaseModel):
    alias: str = Field(description="脱敏代号（如 同学#0421）")
    major: str = ""
    grade: str = ""
    avg_score: float = 0
    focus_score: float = 0
    dimensions: dict[str, float] = Field(default_factory=dict)
    match_reason: str = ""


class MatchOutput(BaseModel):
    order_title: str = ""
    focus_dimension: str = ""
    candidates: list[MatchCandidate] = Field(default_factory=list)
    note: str = Field(
        default="候选人为脱敏视图；确认意向后请联系教师/管理员建立对接。",
    )


class MatchAgent(Agent):
    name = "match"
    input_schema = MatchInput
    output_schema = MatchOutput
    # 规则化打分，不调用 LLM（透明、零成本、可复核）
    use_llm = False

    async def run(self, payload: MatchInput, ctx: AgentContext) -> MatchOutput:
        # 权限：学生不可用（防探查他人能力数据）；企业仅限自己的工单
        if ctx.user.role == "student":
            raise HTTPException(
                status_code=403,
                detail={"code": 40301, "message": "学生不可使用人才匹配"},
            )
        order = (
            await ctx.db.execute(select(WorkOrder).where(WorkOrder.id == payload.order_id))
        ).scalar_one_or_none()
        if order is None:
            raise HTTPException(
                status_code=404, detail={"code": 40401, "message": "工单不存在"}
            )
        if ctx.user.role == "enterprise" and order.enterprise_id != ctx.user.id:
            raise HTTPException(
                status_code=403,
                detail={"code": 40301, "message": "只能对自己发布的工单做人才匹配"},
            )

        req = order.requirements_json or {}
        # 侧重维度：由需求字段推导（题材→内容创作，市场/语言→跨文化，交付→运营）
        focus_dim = next(
            (FOCUS_DIMENSIONS[k] for k in FOCUS_DIMENSIONS if req.get(k)),
            "内容创作",
        )

        # 在读学生 + 档案（脱敏在输出层做，查询层不泄露给前端）
        rows = (
            await ctx.db.execute(
                select(User, StudentProfile)
                .join(StudentProfile, StudentProfile.user_id == User.id)
                .where(User.role == "student", User.status == 1)
            )
        ).all()

        ability_map = await latest_scores_by_students(
            ctx.db, [user.id for user, _ in rows]
        )

        candidates: list[MatchCandidate] = []
        for user, profile in rows:
            dims = ability_map.get(user.id, {})
            if not dims:
                continue  # 无任何评分数据的学生不进入推荐
            avg = round(sum(dims.values()) / len(dims), 2)
            focus_score = round(dims.get(focus_dim, 0), 2)
            score = avg * 0.7 + focus_score * 0.3
            strong = [d for d in DIMENSION_LABELS if dims.get(d, 0) >= 80]
            reason = f"五维均分 {avg}；{focus_dim} {focus_score} 分"
            if strong:
                reason += f"；擅长 {'、'.join(strong)}"
            candidates.append(
                MatchCandidate(
                    alias=f"同学#{str(user.id).zfill(4)}",
                    major=profile.major or "",
                    grade=profile.grade or "",
                    avg_score=avg,
                    focus_score=focus_score,
                    dimensions={d: round(dims.get(d, 0), 1) for d in DIMENSION_LABELS},
                    match_reason=reason,
                )
            )

        candidates.sort(key=lambda c: (c.avg_score * 0.7 + c.focus_score * 0.3), reverse=True)
        return MatchOutput(
            order_title=order.title,
            focus_dimension=focus_dim,
            candidates=candidates[: payload.top_n],
        )
