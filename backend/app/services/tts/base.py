"""TTS Provider 抽象。

实现方返回 (音频字节, 时长毫秒)；Edge-TTS 走官方 websocket，
mock 桩用 ffmpeg 生成静音音频（无网络/密钥环境下联调用）。
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
    def synthesize(self, text: str, voice: str, rate: str = "+0%") -> TTSResult: ...
