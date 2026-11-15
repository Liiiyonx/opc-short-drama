"""优化建议 Agent（optimize）：复盘报告 → 下一轮迭代建议。

契约（docs/05，P1 补齐）：输入为数据分析 Agent 的产出（或人工摘要），
输出按优先级排序的改进建议与下一部剧选题方向。与 analyze 组成"数据回流"闭环。
"""
import json

from pydantic import BaseModel, Field

from app.agents.base import Agent, AgentContext
from app.services.llm.client import chat_json


class OptimizeInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    target_market: str = Field(default="北美")
    analysis: dict = Field(description="数据分析 Agent 的输出（summary/highlights/issues/metrics_read）")
    focus: str = Field(default="", max_length=300, description="学生希望优先改进的方向（选填）")


class Suggestion(BaseModel):
    area: str = Field(description="改进领域：选题/节奏/封面/文案/投放/互动")
    action: str = Field(description="具体可执行的动作")
    priority: str = Field(default="中", description="高 / 中 / 低")
    expected: str = Field(default="", description="预期效果")


class OptimizeOutput(BaseModel):
    suggestions: list[Suggestion] = Field(min_length=1)
    next_topics: list[str] = Field(default_factory=list, description="下一部剧选题方向（2-4 个）")
    learning_goals: list[str] = Field(default_factory=list, description="学生应补强的能力点（对接五维能力）")


class OptimizeAgent(Agent):
    name = "optimize"
    input_schema = OptimizeInput
    output_schema = OptimizeOutput
    system_prompt_file = "optimize_v1.md"

    async def run(self, payload: OptimizeInput, ctx: AgentContext) -> OptimizeOutput:
        system = self.load_system_prompt()
        user_message = json.dumps(payload.model_dump(mode="json"), ensure_ascii=False)
        data, usage = await chat_json(system=system, user=user_message, agent_type=self.name)
        ctx.usage.update(usage)
        output = self.output_schema.model_validate(data)
        # 容错：priority 归一化到 高/中/低
        valid = {"高", "中", "低"}
        for s in output.suggestions:
            if s.priority not in valid:
                s.priority = "中"
        return output
