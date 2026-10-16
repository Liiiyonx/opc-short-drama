"""TTS Provider 抽象。

实现方异步返回 (音频字节, 时长毫秒)。

重要：接口必须是 async —— 智能体在 arq worker 的事件循环内执行，
同步实现里若用 asyncio.run() 会抛「cannot be called from a running
event loop」；edge-tts 本身是异步库，直接 await 即可。
"""
from dataclasses import dataclass
from typing import Protocol


@dataclass
class TTSResult:
    audio: bytes
    duration_ms: int
    voice: str
    mime: str = "audio/mpeg"


class TTSProvider(Protocol):
    async def synthesize(
        self, text: str, voice: str, rate: str = "+0%"
    ) -> TTSResult: ...
