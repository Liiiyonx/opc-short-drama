"""数据分析 Agent（analyze）：播放数据 → 结构化复盘报告。

契约（docs/05，P1 补齐）：输入为发布后人工回填的播放数据
（平台 API 未接入前由学生在成片面板填写），输出中文复盘报告供教师评审与优化建议 Agent 消费。
"""
import json

from pydantic import BaseModel, Field

from app.agents.base import Agent, AgentContext
from app.services.llm.client import chat_json


class PlayStats(BaseModel):
    views: int = Field(default=0, ge=0, description="播放量")
    likes: int = Field(default=0, ge=0)
    comments: int = Field(default=0, ge=0)
    shares: int = Field(default=0, ge=0)
    completion_rate: float = Field(default=0, ge=0, le=1, description="完播率 0-1")
    avg_watch_seconds: float = Field(default=0, ge=0, description="平均观看秒数")


class AnalyzeInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    platform: str = Field(default="TikTok")
    target_market: str = Field(default="北美")
    duration_seconds: float = Field(default=0, ge=0)
    stats: PlayStats
    notes: str = Field(default="", max_length=500, description="发布备注（投放时间/标签等）")


class AnalyzeOutput(BaseModel):
    summary: str = Field(description="一段话整体复盘")
    highlights: list[str] = Field(default_factory=list, description="做对了什么")
    issues: list[str] = Field(default_factory=list, description="问题诊断")
    metrics_read: list[str] = Field(default_factory=list, description="关键指标解读（含计算过程）")
    verdict: str = Field(description="一句话结论：值得加投 / 调整后再投 / 建议换方向")


class AnalyzeAgent(Agent):
    name = "analyze"
    input_schema = AnalyzeInput
    output_schema = AnalyzeOutput
    system_prompt_file = "analyze_v1.md"

    async def run(self, payload: AnalyzeInput, ctx: AgentContext) -> AnalyzeOutput:
        system = self.load_system_prompt()
        user_message = json.dumps(payload.model_dump(mode="json"), ensure_ascii=False)
        data, usage = await chat_json(system=system, user=user_message, agent_type=self.name)
        ctx.usage.update(usage)
        return self.output_schema.model_validate(data)
