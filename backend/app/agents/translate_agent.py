"""翻译本地化 Agent（translate）：台词批量本地化 + 文化注释 + 合规标记。

契约（docs/05 §3.4，2026-10-16 由单文本升级为批量——保上下文连贯且省调用）：
- 输入：{lines: [{line_id, text, role?}], source_lang?, target_locale}
- 输出：{lines: [{line_id, translated}], notes[], compliance_flags[], target_locale}
由商务英语专业主导使用：跨文化改写、俚语适配、敏感词与文化禁忌标记。
容错：模型漏输出的行以原文兜底（并在输出行数不齐时保住链路）。
"""
import json

from pydantic import BaseModel, Field

from app.agents.base import Agent, AgentContext
from app.services.llm.client import chat_json


class TranslateLine(BaseModel):
    line_id: int
    text: str
    role: str = "narrator"


class TranslateInput(BaseModel):
    lines: list[TranslateLine] = Field(min_length=1)
    source_lang: str = Field(default="auto", description="源语言，auto 自动判断")
    target_locale: str = Field(
        default="en-US", description="目标语言/地区，如 en-US / ja-JP / ar-EG"
    )
    context: str = Field(default="short_drama", description="使用场景")


class TranslatedLine(BaseModel):
    line_id: int
    translated: str


class ComplianceFlag(BaseModel):
    line_id: int | None = None
    issue: str
    suggestion: str = ""
    severity: str = "medium"


class TranslateOutput(BaseModel):
    lines: list[TranslatedLine]
    notes: list[str] = Field(default_factory=list)
    compliance_flags: list[ComplianceFlag] = Field(default_factory=list)
    target_locale: str = ""


class TranslateAgent(Agent):
    name = "translate"
    input_schema = TranslateInput
    output_schema = TranslateOutput
    system_prompt_file = "translate_v1.md"

    async def run(self, payload: TranslateInput, ctx: AgentContext) -> TranslateOutput:
        system = self.load_system_prompt()
        user_message = json.dumps(payload.model_dump(mode="json"), ensure_ascii=False)
        data, usage = await chat_json(
            system=system, user=user_message, agent_type=self.name
        )
        ctx.usage.update(usage)
        # 容错①：模型偶尔把译文写回输入结构（text 字段）而非 translated → 归一化
        # （实测 2026-10-16 真实 DeepSeek 偶发：输入输出结构相似时回显输入模板）
        if isinstance(data, dict) and isinstance(data.get("lines"), list):
            for item in data["lines"]:
                if (
                    isinstance(item, dict)
                    and "translated" not in item
                    and "text" in item
                ):
                    item["translated"] = item["text"]
        output = self.output_schema.model_validate(data)
        # 容错②：模型漏输出的行以原文兜底，保 line_id 齐全与顺序
        by_id = {item.line_id: item.translated for item in output.lines}
        output.lines = [
            TranslatedLine(
                line_id=line.line_id,
                translated=by_id.get(line.line_id, line.text),
            )
            for line in payload.lines
        ]
        output.target_locale = payload.target_locale
        return output
