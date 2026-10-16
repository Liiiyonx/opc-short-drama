"""音色映射与市场→语言映射（docs/05 §3.3）。

音色名核对于 Edge-TTS 官方音色清单（2026-10-16 联网核实），
覆盖短剧出海主要市场语言：英/中/日/韩/泰/越/印尼/阿/西/法/葡/马来。
"""
# 角色 × 语言 → Edge-TTS 音色（narrator 使用中性/旁白音色）
VOICE_MAP: dict[str, dict[str, str]] = {
    "narrator": {
        "zh-CN": "zh-CN-XiaoxiaoNeural",
        "en-US": "en-US-AriaNeural",
        "ja-JP": "ja-JP-NanamiNeural",
        "ko-KR": "ko-KR-SunHiNeural",
        "th-TH": "th-TH-PremwadeeNeural",
        "vi-VN": "vi-VN-HoaiMyNeural",
        "id-ID": "id-ID-GadisNeural",
        "ar-EG": "ar-EG-SalmaNeural",
        "ar-SA": "ar-SA-ZariyahNeural",
        "es-MX": "es-MX-DaliaNeural",
        "fr-FR": "fr-FR-DeniseNeural",
        "pt-BR": "pt-BR-FranciscaNeural",
        "ms-MY": "ms-MY-YasminNeural",
    },
    "male": {
        "zh-CN": "zh-CN-YunxiNeural",
        "en-US": "en-US-GuyNeural",
        "ja-JP": "ja-JP-KeitaNeural",
        "ko-KR": "ko-KR-InJoonNeural",
        "th-TH": "th-TH-NiwatNeural",
        "vi-VN": "vi-VN-NamMinhNeural",
        "id-ID": "id-ID-ArdiNeural",
        "ar-EG": "ar-EG-ShakirNeural",
        "ar-SA": "ar-SA-HamedNeural",
        "es-MX": "es-MX-JorgeNeural",
        "fr-FR": "fr-FR-HenriNeural",
        "pt-BR": "pt-BR-AntonioNeural",
        "ms-MY": "ms-MY-OsmanNeural",
    },
    "female": {
        "zh-CN": "zh-CN-XiaohanNeural",
        "en-US": "en-US-JennyNeural",
        "ja-JP": "ja-JP-AoiNeural",
        "ko-KR": "ko-KR-SunHiNeural",
        "th-TH": "th-TH-PremwadeeNeural",
        "vi-VN": "vi-VN-HoaiMyNeural",
        "id-ID": "id-ID-GadisNeural",
        "ar-EG": "ar-EG-SalmaNeural",
        "ar-SA": "ar-SA-ZariyahNeural",
        "es-MX": "es-MX-DaliaNeural",
        "fr-FR": "fr-FR-DeniseNeural",
        "pt-BR": "pt-BR-FranciscaNeural",
        "ms-MY": "ms-MY-YasminNeural",
    },
}

DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"

# 目标市场 → 语言（按子串匹配，细分子市场在前，泛称兜底在后）
MARKET_LANG: dict[str, str] = {
    "北美": "en-US",
    "欧洲": "en-US",
    "印尼": "id-ID",
    "泰国": "th-TH",
    "越南": "vi-VN",
    "马来": "ms-MY",
    "菲律宾": "en-US",
    "日本": "ja-JP",
    "韩国": "ko-KR",
    "日韩": "ja-JP",
    "东南亚": "en-US",
    "中东": "ar-EG",
    "沙特": "ar-SA",
    "拉美": "es-MX",
    "巴西": "pt-BR",
    "法国": "fr-FR",
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
