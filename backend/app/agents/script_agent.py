"""剧本生成 Agent（script）：题材/市场/集数 → 结构化分集大纲。

契约见 docs/05-智能体设计.md §3.1；System Prompt 见 prompts/script_v1.md。
"""
import json

from pydantic import BaseModel, Field

from app.agents.base import Agent, AgentContext
from app.services.llm.client import chat_json


class ScriptInput(BaseModel):
    genre: str = Field(description="题材，如 逆袭/甜宠/悬疑")
    target_market: str = Field(description="目标市场，如 北美/东南亚")
    episodes: int = Field(default=20, ge=1, le=200, description="集数")
    episode_minutes: int = Field(default=2, ge=1, le=10, description="单集分钟数")
    style: str | None = Field(default=None, description="风格模板")
    keywords: list[str] = Field(default_factory=list, description="必须锁定的关键词")
    prev_outline: dict | None = Field(default=None, description="上一版大纲（多轮改写）")
    feedback: str | None = Field(default=None, description="本轮修改反馈")


class ScriptScene(BaseModel):
    scene: int
    location: str
    characters: list[str]
    dialogue: list[str]
    note: str | None = None


class ScriptEpisode(BaseModel):
    ep: int
    title: str
    outline: str
    scenes: list[ScriptScene]


class ScriptOutput(BaseModel):
    title: str
    logline: str
    target_market: str
    episodes: list[ScriptEpisode]


class ScriptAgent(Agent):
    name = "script"
    input_schema = ScriptInput
    output_schema = ScriptOutput
    system_prompt_file = "script_v1.md"

    async def run(self, payload: ScriptInput, ctx: AgentContext) -> ScriptOutput:
        system = self.load_system_prompt()
        user_message = json.dumps(payload.model_dump(mode="json"), ensure_ascii=False)
        data, usage = await chat_json(
            system=system, user=user_message, agent_type=self.name
        )
        ctx.usage.update(usage)
        return self.output_schema.model_validate(data)
