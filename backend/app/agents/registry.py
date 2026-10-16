"""智能体注册表：新增智能体 = 加一个类 + 在这里注册一行。"""
from fastapi import HTTPException

from app.agents.base import Agent
from app.agents.compose_agent import ComposeAgent
from app.agents.publish_agent import PublishAgent
from app.agents.script_agent import ScriptAgent
from app.agents.storyboard_agent import StoryboardAgent
from app.agents.translate_agent import TranslateAgent
from app.agents.tts_agent import TTSAgent

AGENTS: dict[str, type[Agent]] = {
    "script": ScriptAgent,
    "storyboard": StoryboardAgent,
    "translate": TranslateAgent,
    "tts": TTSAgent,
    "compose": ComposeAgent,
    "publish": PublishAgent,
}


def get_agent_class(agent_type: str) -> type[Agent]:
    cls = AGENTS.get(agent_type)
    if cls is None:
        available = ", ".join(sorted(AGENTS))
        raise HTTPException(
            status_code=404,
            detail={"code": 40401, "message": f"未知智能体类型：{agent_type}（当前可用：{available}）"},
        )
    return cls
