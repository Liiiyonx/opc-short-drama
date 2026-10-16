"""作品相关入参出参（W3）。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WorkCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    type: str = Field(pattern="^(script|storyboard|translate|audio|subtitle|video)$")
    task_id: int | None = None


class GenerateIn(BaseModel):
    """生成参数：按作品类型取用相应字段（细校验在服务层/智能体契约）。"""

    model_config = ConfigDict(extra="allow")

    # 剧本参数
    genre: str | None = None
    target_market: str | None = None
    episodes: int | None = None
    episode_minutes: int | None = None
    style: str | None = None
    keywords: list[str] | None = None
    prev_outline: dict | None = None
    feedback: str | None = None
    # 分镜参数
    source_work_id: int | None = None
    episode: int | None = None
    aspect_ratio: str | None = None
    style_hint: str | None = None
    target_seconds: int | None = None
    # 配音参数
    storyboard_work_id: int | None = None
    lang: str | None = None
    voice_map: dict | None = None
    # 翻译参数
    target_locale: str | None = None
    # 视频参数
    audio_work_id: int | None = None
    width: int | None = None
    height: int | None = None


class PublishParamsIn(BaseModel):
    """发布参数生成入参（挂成片作品）。"""

    source_work_id: int | None = Field(default=None, description="剧本作品 id（取剧名/梗概/市场）")
    platforms: list[str] | None = Field(default=None, description="目标平台，缺省用默认三平台")


class RevisionIn(BaseModel):
    """人工修订产物（初终稿差异比对：字幕校轴等）。"""

    kind: str = Field(default="srt", pattern="^(srt|text)$")
    content: str = Field(min_length=1)


class TextAssetIn(BaseModel):
    kind: str = Field(pattern="^(text|json|srt)$")
    content: str
    filename: str | None = None


class AiDeclareIn(BaseModel):
    agents_used: list[str] = Field(default_factory=list)
    human_edit_ratio: float | None = Field(default=None, ge=0, le=1)
    note: str | None = None


class WorkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    type: str
    version: int
    status: str
    parent_id: int | None = None
    task_id: int | None = None
    meta_json: dict | None = None
    ai_declare_json: dict | None = None
    created_at: datetime | None = None


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    storage_key: str
    mime: str | None = None
    size: int | None = None
    duration_ms: int | None = None
    url: str = ""
    created_at: datetime | None = None
