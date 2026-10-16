"""Mock TTS Provider：ffmpeg 生成静音 MP3。

仅在 TTS_PROVIDER=mock 显式启用时使用（无网络/密钥联调、pytest），
按文本长度估算时长，保证 SRT 时间轴与后续合成可被真实验证。

异步接口与 EdgeTTSProvider 保持一致；ffmpeg 子进程走线程池不阻塞事件循环。
"""
import asyncio

from app.services.media import render_silence_mp3
from app.services.tts.base import TTSResult


def estimate_duration_ms(text: str) -> int:
    """中文约 4.5 字/秒，英文约 15 字符/秒；保底 1 秒。"""
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other = len(text) - cjk
    seconds = cjk / 4.5 + other / 15.0
    return max(1000, int(seconds * 1000))


class MockTTSProvider:
    async def synthesize(
        self, text: str, voice: str, rate: str = "+0%"
    ) -> TTSResult:
        duration_ms = estimate_duration_ms(text)
        audio = await asyncio.to_thread(render_silence_mp3, duration_ms / 1000)
        return TTSResult(audio=audio, duration_ms=duration_ms, voice=voice)
