"""发布参数 Agent（publish）：成片 → 各平台上架参数包。

契约（docs/05 §4，P0 落地"仅生成发布参数"）：
- 输入：{title, target_market, synopsis?, genre?, duration_seconds, platforms?}
- 输出：{platforms[], compliance_checklist[], resolution_note}
产物落写为作品资产（kind=publish_params，JSON），前端一键复制使用。
"""
import json

from pydantic import BaseModel, Field

from app.agents.base import Agent, AgentContext
from app.services.llm.client import chat_json
from app.services.work_store import save_asset

DEFAULT_PLATFORMS = ["TikTok", "YouTube Shorts", "ReelShort"]


class PublishInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    target_market: str = Field(default="北美")
    synopsis: str = ""
    genre: str | None = None
    duration_seconds: float = Field(default=0, ge=0)
    platforms: list[str] = Field(default_factory=lambda: list(DEFAULT_PLATFORMS))


class PublishPlatform(BaseModel):
    name: str
    title: str
    caption: str = ""
    hashtags: list[str] = Field(default_factory=list)
    best_time: str = ""
    notes: str = ""


class PublishOutput(BaseModel):
    platforms: list[PublishPlatform]
    compliance_checklist: list[str] = Field(default_factory=list)
    resolution_note: str = ""


class PublishAgent(Agent):
    name = "publish"
    input_schema = PublishInput
    output_schema = PublishOutput
    system_prompt_file = "publish_v1.md"

    async def run(self, payload: PublishInput, ctx: AgentContext) -> PublishOutput:
        system = self.load_system_prompt()
        user_message = json.dumps(payload.model_dump(mode="json"), ensure_ascii=False)
        data, usage = await chat_json(
            system=system, user=user_message, agent_type=self.name
        )
        ctx.usage.update(usage)
        output = self.output_schema.model_validate(data)
        # 产物存入当前成片作品的资产（JSON），供前端展示与复制
        if ctx.work_id is not None:
            content = json.dumps(
                output.model_dump(mode="json"), ensure_ascii=False
            ).encode("utf-8")
            await save_asset(
                ctx.db, ctx.work_id, "publish_params", content, "application/json"
            )
        return output
