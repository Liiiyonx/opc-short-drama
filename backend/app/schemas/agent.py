"""智能体相关出参。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AgentSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_type: str
    status: str
    input_json: dict | None = None
    output_json: dict | None = None
    error: str | None = None
    work_id: int | None = None
    created_at: datetime | None = None
    finished_at: datetime | None = None
