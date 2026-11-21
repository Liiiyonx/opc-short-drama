"""成片合成 Agent（compose）：分镜图 + 配音 + SRT → 烧字幕 MP4（异步）。

图片来源：分镜作品的 image 资产（用户在 W3 上传接口上传）；
无上传时按镜头数生成确定性演示帧（渐变构图 + 镜头信息，非纯色）。
is_async=True，由 arq worker 执行（ffmpeg CPU 密集）。

P0-08 成片质检：合成后自动过 video_qc_report（黑帧/纯色帧/削波/音轨），
结果写入 output.qc；不通过时产物仍落库但会话日志明确标记，演示前可追溯。

阻塞调用（ffmpeg/ffprobe 子进程）统一走 asyncio.to_thread，
避免卡住 worker 事件循环影响其他并发任务。
"""
import asyncio

from pydantic import BaseModel, Field

from app.agents.base import Agent, AgentContext
from app.core.config import get_settings
from app.services.media import (
    MediaError,
    burn_video,
    probe_duration_ms,
    scene_frame_png,
    video_qc_report,
)
from app.services.work_store import (
    latest_asset,
    latest_json_asset,
    list_assets,
    load_my_work,
    save_asset,
)
from app.services.storage.factory import get_storage


class ComposeInput(BaseModel):
    storyboard_work_id: int
    audio_work_id: int
    width: int = Field(default=720, ge=180, le=1920)
    height: int = Field(default=1280, ge=180, le=1920)


class ComposeOutput(BaseModel):
    video_key: str | None = None
    duration_ms: int = 0
    images_used: int = 0
    placeholder: bool = False
    qc: dict = Field(default_factory=dict, description="成片质检报告（pass/issues/stats）")


class ComposeAgent(Agent):
    name = "compose"
    input_schema = ComposeInput
    output_schema = ComposeOutput
    is_async = True

    async def run(self, payload: ComposeInput, ctx: AgentContext) -> ComposeOutput:
        ctx.usage.update(
            {"provider": "ffmpeg", "model": "", "prompt_tokens": 0, "completion_tokens": 0}
        )
        storyboard = await load_my_work(ctx.db, ctx.user, payload.storyboard_work_id)
        audio_work = await load_my_work(ctx.db, ctx.user, payload.audio_work_id)

        shots = await latest_json_asset(ctx.db, storyboard.id)
        if not shots or not shots.get("shots"):
            raise MediaError("分镜作品没有产物，请先执行分镜生成")

        merged_asset = await latest_asset(ctx.db, audio_work.id, "audio_merged")
        srt_asset = await latest_asset(ctx.db, audio_work.id, "srt")
        if merged_asset is None or srt_asset is None:
            raise MediaError("配音作品缺少合并音轨或 SRT，请先执行配音生成")

        storage = get_storage()
        audio_bytes = storage.get_bytes(merged_asset.storage_key)
        srt_text = storage.get_bytes(srt_asset.storage_key).decode("utf-8")

        image_assets = await list_assets(ctx.db, storyboard.id, "image")
        placeholder = not image_assets
        if placeholder:
            shots_list = shots["shots"]
            images = list(
                await asyncio.gather(
                    *(
                        asyncio.to_thread(
                            scene_frame_png,
                            index,
                            payload.width,
                            payload.height,
                            f"Scene {shot.get('scene', index + 1)} · {shot.get('shot_size', '')}",
                            shot.get("dialogue", "") or shot.get("visual_prompt", ""),
                        )
                        for index, shot in enumerate(shots_list)
                    )
                )
            )
        else:
            images = [storage.get_bytes(asset.storage_key) for asset in image_assets]

        video_bytes = await asyncio.to_thread(
            burn_video, images, audio_bytes, srt_text, payload.width, payload.height
        )
        duration_ms = await asyncio.to_thread(probe_duration_ms, video_bytes, ".mp4")
        qc = await asyncio.to_thread(video_qc_report, video_bytes)
        if not qc.get("pass"):
            # 质检不过不阻断落库（保持链路可演示），但显式暴露问题供人工修复
            ctx.usage["qc_issues"] = "; ".join(qc.get("issues", []))
        _, video_key = await save_asset(
            ctx.db,
            ctx.work_id,
            "video",
            video_bytes,
            "video/mp4",
            duration_ms=duration_ms,
        )
        return ComposeOutput(
            video_key=video_key,
            duration_ms=duration_ms,
            images_used=len(images),
            placeholder=placeholder,
            qc=qc,
        )
