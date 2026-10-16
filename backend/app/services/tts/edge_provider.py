"""Edge-TTS Provider（生产默认，免密钥多语种）。"""
import asyncio
import tempfile
from pathlib import Path

from app.services.media import probe_duration_ms
from app.services.tts.base import TTSResult


class EdgeTTSProvider:
    """基于 edge-tts 官方库的合成器；输出 MP3。"""

    def synthesize(self, text: str, voice: str, rate: str = "+0%") -> TTSResult:
        import edge_tts

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        async def _run() -> None:
            communicate = edge_tts.Communicate(text, voice, rate=rate)
            await communicate.save(str(tmp_path))

        try:
            asyncio.run(_run())
            audio = tmp_path.read_bytes()
            duration_ms = probe_duration_ms(audio, ".mp3")
            return TTSResult(audio=audio, duration_ms=duration_ms, voice=voice)
        finally:
            tmp_path.unlink(missing_ok=True)
