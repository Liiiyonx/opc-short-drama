"""音色映射与市场→语言映射（docs/05 §3.3）。"""

# 角色 × 语言 → Edge-TTS 音色
VOICE_MAP: dict[str, dict[str, str]] = {
    "narrator": {
        "zh-CN": "zh-CN-XiaoxiaoNeural",
        "en-US": "en-US-AriaNeural",
        "ja-JP": "ja-JP-NanamiNeural",
        "es-MX": "es-MX-DaliaNeural",
        "ar-EG": "ar-EG-SalmaNeural",
    },
    "male": {
        "zh-CN": "zh-CN-YunxiNeural",
        "en-US": "en-US-GuyNeural",
        "ja-JP": "ja-JP-KeitaNeural",
        "es-MX": "es-MX-JorgeNeural",
        "ar-EG": "ar-EG-ShakirNeural",
    },
    "female": {
        "zh-CN": "zh-CN-XiaohanNeural",
        "en-US": "en-US-JennyNeural",
        "ja-JP": "ja-JP-AoiNeural",
        "es-MX": "es-MX-DaliaNeural",
        "ar-EG": "ar-EG-SalmaNeural",
    },
}

DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"

# 目标市场 → 语言（短剧出海常用市场）
MARKET_LANG: dict[str, str] = {
    "北美": "en-US",
    "欧洲": "en-US",
    "东南亚": "zh-CN",
    "日韩": "ja-JP",
    "中东": "ar-EG",
    "拉美": "es-MX",
}


def pick_voice(role: str, lang: str, voice_map: dict | None = None) -> str:
    """优先用户显式 voice_map（{role: voice}），再按角色×语言内置表。

    未知角色回退到该语言的旁白音色；未知语言回退默认音色。
    """
    if voice_map and role in voice_map:
        return voice_map[role]
    narrator_voice = VOICE_MAP["narrator"].get(lang)
    return (
        VOICE_MAP.get(role, {}).get(lang)
        or narrator_voice
        or DEFAULT_VOICE
    )


def market_to_lang(target_market: str | None) -> str:
    if not target_market:
        return "zh-CN"
    for key, lang in MARKET_LANG.items():
        if key in target_market:
            return lang
    return "zh-CN"
