"""配音 Agent（tts）：台词行 → 逐行音频 + 合并音轨 + SRT 字幕（异步）。

契约见 docs/05-智能体设计.md §3.3；is_async=True，由 arq worker 执行。
音色映射见 services/tts/voices.py；SRT 时间轴按逐行真实时长累加。
"""
from pydantic import BaseModel, Field

from app.agents.base import Agent, AgentContext
from app.core.config import get_settings
from app.services.media import build_srt, concat_audio
from app.services.tts.factory import get_tts_provider
from app.services.tts.voices import pick_voice
from app.services.work_store import save_asset


class TTSLine(BaseModel):
    line_id: int
    role: str = "narrator"
    text: str
    lang: str = "zh-CN"


class TTSInput(BaseModel):
    lines: list[TTSLine] = Field(min_length=1)
    voice_map: dict | None = Field(default=None, description="{role: voice} 覆盖")


class TTSAsset(BaseModel):
    line_id: int
    audio_key: str
    duration_ms: int


class TTSOutput(BaseModel):
    assets: list[TTSAsset]
    merged_audio_key: str | None = None
    srt_key: str | None = None
    total_duration_ms: int = 0


class TTSAgent(Agent):
    name = "tts"
    input_schema = TTSInput
    output_schema = TTSOutput
    is_async = True

    async def run(self, payload: TTSInput, ctx: AgentContext) -> TTSOutput:
        provider = get_tts_provider()
        ctx.usage.update(
            {"provider": get_settings().tts_provider, "model": "", "prompt_tokens": 0, "completion_tokens": 0}
        )

        assets: list[TTSAsset] = []
        parts: list[bytes] = []
        cues: list[dict] = []
        cursor_ms = 0

        for line in payload.lines:
            voice = pick_voice(line.role, line.lang, payload.voice_map)
            result = provider.synthesize(line.text, voice)
            _, audio_key = await save_asset(
                ctx.db,
                ctx.work_id,
                "audio",
                result.audio,
                "audio/mpeg",
                duration_ms=result.duration_ms,
            )
            assets.append(
                TTSAsset(
                    line_id=line.line_id,
                    audio_key=audio_key,
                    duration_ms=result.duration_ms,
                )
            )
            parts.append(result.audio)
            cues.append(
                {
                    "start_ms": cursor_ms,
                    "end_ms": cursor_ms + result.duration_ms,
                    "text": line.text,
                }
            )
            cursor_ms += result.duration_ms

        srt_text = build_srt(cues)
        _, srt_key = await save_asset(
            ctx.db, ctx.work_id, "srt", srt_text.encode("utf-8"), "text/plain"
        )

        merged_key = None
        if parts:
            merged = concat_audio(parts)
            _, merged_key = await save_asset(
                ctx.db,
                ctx.work_id,
                "audio_merged",
                merged,
                "audio/mpeg",
                duration_ms=cursor_ms,
            )

        return TTSOutput(
            assets=assets,
            merged_audio_key=merged_key,
            srt_key=srt_key,
            total_duration_ms=cursor_ms,
        )
