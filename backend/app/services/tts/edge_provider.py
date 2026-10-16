"""Edge-TTS Provider（生产默认，免密钥多语种）。

异步实现：edge-tts 走官方 websocket，原生 async。
- 行级重试：websocket 偶发抖动时最多重试 3 次（指数退避）；
- ffprobe 时长探测放线程池（subprocess 阻塞，勿卡事件循环）。
"""
import asyncio
import tempfile
from pathlib import Path

from app.services.media import probe_duration_ms
from app.services.tts.base import TTSResult


class EdgeTTSProvider:
    """基于 edge-tts 官方库的合成器；输出 MP3。"""

    def __init__(self, max_attempts: int = 3) -> None:
        self.max_attempts = max_attempts

    async def synthesize(
        self, text: str, voice: str, rate: str = "+0%"
    ) -> TTSResult:
        import edge_tts

        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            try:
                communicate = edge_tts.Communicate(text, voice, rate=rate)
                await communicate.save(str(tmp_path))
                audio = tmp_path.read_bytes()
                if not audio:
                    raise RuntimeError("edge-tts 返回空音频")
                duration_ms = await asyncio.to_thread(
                    probe_duration_ms, audio, ".mp3"
                )
                return TTSResult(audio=audio, duration_ms=duration_ms, voice=voice)
            except Exception as exc:  # noqa: BLE001 网络类异常统一重试
                last_error = exc
                if attempt < self.max_attempts - 1:
                    await asyncio.sleep(1.0 * (attempt + 1))
            finally:
                tmp_path.unlink(missing_ok=True)
        raise RuntimeError(f"edge-tts 合成失败（重试 {self.max_attempts} 次）：{last_error}")
