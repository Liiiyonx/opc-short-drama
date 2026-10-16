"""配音 Agent（tts）：台词行 → 逐行音频 + 合并音轨 + SRT 字幕（异步）。

契约见 docs/05-智能体设计.md §3.3；is_async=True，由 arq worker 执行。
音色映射见 services/tts/voices.py；SRT 时间轴按逐行真实时长累加。

性能：逐行合成走 asyncio.gather + 并发上限（TTS_CONCURRENCY），
20 行台词从串行 N×1s 降到 ~N/4×1s；DB 写入保持串行
（AsyncSession 不可并发使用），顺序与 gather 输入一致。
"""
import asyncio

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
            {
                "provider": get_settings().tts_provider,
                "model": "",
                "prompt_tokens": 0,
                "completion_tokens": 0,
            }
        )

        # 并行合成（保序：gather 按输入顺序返回）
        semaphore = asyncio.Semaphore(max(1, get_settings().tts_concurrency))

        async def _synth(line: TTSLine):
            voice = pick_voice(line.role, line.lang, payload.voice_map)
            async with semaphore:
                result = await provider.synthesize(line.text, voice)
            return line, result

        synthesized = await asyncio.gather(
            *(_synth(line) for line in payload.lines)
        )

        # 串行落库 + 构建 SRT 时间轴
        assets: list[TTSAsset] = []
        parts: list[bytes] = []
        cues: list[dict] = []
        cursor_ms = 0
        for line, result in synthesized:
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
            merged = await asyncio.to_thread(concat_audio, parts)
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
