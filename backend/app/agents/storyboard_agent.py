"""分镜 Agent（storyboard）：单集剧本 → 镜头列表。

契约见 docs/05-智能体设计.md §3.2；System Prompt 见 prompts/storyboard_v1.md。
"""
import json

from pydantic import BaseModel, Field

from app.agents.base import Agent, AgentContext
from app.services.llm.client import chat_json


class StoryboardInput(BaseModel):
    episode_script: dict = Field(description="单集剧本（ScriptOutput.episodes 的元素）")
    aspect_ratio: str = Field(default="9:16", description="画幅比例")
    style_hint: str | None = Field(default=None, description="风格提示，如 写实/动漫")
    target_seconds: int = Field(default=120, ge=30, le=600, description="目标单集秒数")


class StoryboardShot(BaseModel):
    shot_no: int
    scene: int
    shot_size: str = Field(description="景别：特写/近景/中景/全景")
    camera_move: str = Field(description="运镜：推/拉/摇/移/固定")
    visual_prompt: str = Field(description="英文画面提示词")
    dialogue: str = ""
    duration_sec: int


class StoryboardOutput(BaseModel):
    shots: list[StoryboardShot]


class StoryboardAgent(Agent):
    name = "storyboard"
    input_schema = StoryboardInput
    output_schema = StoryboardOutput
    system_prompt_file = "storyboard_v1.md"

    async def run(self, payload: StoryboardInput, ctx: AgentContext) -> StoryboardOutput:
        system = self.load_system_prompt()
        user_message = json.dumps(payload.model_dump(mode="json"), ensure_ascii=False)
        data, usage = await chat_json(
            system=system, user=user_message, agent_type=self.name
        )
        ctx.usage.update(usage)
        return self.output_schema.model_validate(data)
