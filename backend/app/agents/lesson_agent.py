"""AI 备课助手 Agent（lesson）：课程主题 → 教案 / 讨论题 / 实训题目 / Rubric 建议。

契约（docs/05 §5.2，P1 补齐）：教师端 AI 辅助备课。产出可二次编辑后发布，
坚持"AI 辅助而非替代"——输出仅是草案。
"""
import json

from pydantic import BaseModel, Field

from app.agents.base import Agent, AgentContext
from app.services.llm.client import chat_json


class LessonInput(BaseModel):
    course_name: str = Field(min_length=1, max_length=100, description="课程名，如 AIGC 跨境内容创作")
    topic: str = Field(min_length=1, max_length=200, description="本次课主题")
    audience: str = Field(default="应用型本科 电商/商务英语专业", max_length=100)
    duration_minutes: int = Field(default=45, ge=20, le=240)
    tools: list[str] = Field(default_factory=list, description="本课要用的平台智能体（选填）")


class OutlineSection(BaseModel):
    section: str
    minutes: int
    content: str


class LessonOutput(BaseModel):
    objectives: list[str] = Field(min_length=1, description="教学目标（3-4 条）")
    outline: list[OutlineSection] = Field(min_length=1, description="课堂环节（时间合计≈duration_minutes）")
    discussion_questions: list[str] = Field(default_factory=list)
    assignment: str = Field(default="", description="课后实训任务建议")
    rubric_suggestion: list[dict] = Field(
        default_factory=list,
        description='建议评分项 [{name, dimension, weight}]，dimension ∈ 五维能力',
    )


class LessonAgent(Agent):
    name = "lesson"
    input_schema = LessonInput
    output_schema = LessonOutput
    system_prompt_file = "lesson_v1.md"

    async def run(self, payload: LessonInput, ctx: AgentContext) -> LessonOutput:
        system = self.load_system_prompt()
        user_message = json.dumps(payload.model_dump(mode="json"), ensure_ascii=False)
        data, usage = await chat_json(system=system, user=user_message, agent_type=self.name)
        ctx.usage.update(usage)
        output = self.output_schema.model_validate(data)
        # 容错：outline 时间合计若与输入偏差过大，按比例归一到 duration_minutes
        if payload.duration_minutes and output.outline:
            total = sum(s.minutes for s in output.outline)
            if total and abs(total - payload.duration_minutes) > 5:
                ratio = payload.duration_minutes / total
                for s in output.outline:
                    s.minutes = max(1, round(s.minutes * ratio))
        return output
