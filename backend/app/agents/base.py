"""智能体框架基类。

每个智能体 = 一个类，声明 name / input_schema / output_schema，
实现 run()。Pydantic 契约即文档（docs/05-智能体设计.md）。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


@dataclass
class AgentContext:
    """一次智能体调用的执行上下文。"""

    db: AsyncSession
    user: User
    work_id: int | None = None
    session_id: int | None = None  # 无作品直调时作为存储键前缀
    # 由 agent 在 run() 内填充：provider / model / prompt_tokens / completion_tokens
    usage: dict = field(default_factory=dict)


class Agent(ABC):
    name: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    system_prompt_file: str | None = None
    is_async: bool = False  # 异步智能体走 arq 队列（tts/compose）

    @abstractmethod
    async def run(self, payload: BaseModel, ctx: AgentContext) -> BaseModel:
        """执行智能体，返回经 output_schema 校验的结构化结果。"""

    def load_system_prompt(self) -> str:
        if not self.system_prompt_file:
            return ""
        path = Path(__file__).parent / "prompts" / self.system_prompt_file
        return path.read_text(encoding="utf-8")
