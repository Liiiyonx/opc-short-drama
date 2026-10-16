"""TTS 工厂：按 TTS_PROVIDER 返回 Provider（edge-tts / mock）。"""
from functools import lru_cache

from app.core.config import get_settings
from app.services.tts.base import TTSProvider


@lru_cache
def get_tts_provider() -> TTSProvider:
    settings = get_settings()
    if settings.tts_provider == "mock":
        from app.services.tts.mock import MockTTSProvider

        return MockTTSProvider()
    from app.services.tts.edge_provider import EdgeTTSProvider

    return EdgeTTSProvider()
