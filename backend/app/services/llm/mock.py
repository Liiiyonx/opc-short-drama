"""LLM mock 测试桩。

仅在 LLM_PROVIDER=mock 显式启用时使用，用于无密钥环境下联调与 pytest。
返回符合剧本 Agent 输出契约的固定 JSON，让整条链路（校验→配额→
会话→日志→成本估算）可被真实执行验证。这不是回退路径。
"""
import json

from app.services.llm.router import ModelRoute

MOCK_SCRIPT_OUTPUT = {
    "title": "《外卖箱里的秘密》",
    "logline": "被开除的外卖员无意中发现客户的餐盒里藏着改变命运的证据。",
    "target_market": "北美",
    "episodes": [
        {
            "ep": 1,
            "title": "最后一单",
            "outline": "被平台开除当天，林越接到最后一单，客户却刻意避开门缝取餐。",
            "scenes": [
                {
                    "scene": 1,
                    "location": "老旧小区楼道",
                    "characters": ["林越", "神秘客户"],
                    "dialogue": ["你的餐。", "放地上，别过来。"],
                    "note": "开场 3 秒钩子：客户只露一只手，指节有伤",
                }
            ],
        },
        {
            "ep": 2,
            "title": "箱底的字条",
            "outline": "林越回到出租屋翻看外卖箱，发现箱底贴着一张写着暗号的字条。",
            "scenes": [
                {
                    "scene": 1,
                    "location": "出租屋",
                    "characters": ["林越"],
                    "dialogue": ["这箱子……昨天不是空的。"],
                    "note": "结尾反转：字条笔画与客户字迹一致",
                }
            ],
        },
    ],
}


MOCK_STORYBOARD_OUTPUT = {
    "shots": [
        {
            "shot_no": 1,
            "scene": 1,
            "shot_size": "特写",
            "camera_move": "固定",
            "visual_prompt": "close-up of a delivery rider's scarred hand reaching for a paper bag in a dim corridor, warm tungsten light, realistic style",
            "dialogue": "你的餐。",
            "duration_sec": 8,
        },
        {
            "shot_no": 2,
            "scene": 1,
            "shot_size": "近景",
            "camera_move": "推",
            "visual_prompt": "medium shot of a mysterious customer half-hidden behind a door crack, only one hand visible, suspenseful lighting",
            "dialogue": "放地上，别过来。",
            "duration_sec": 10,
        },
        {
            "shot_no": 3,
            "scene": 1,
            "shot_size": "中景",
            "camera_move": "摇",
            "visual_prompt": "rider looking back confused while walking away in an old residential stairwell, morning haze through window",
            "dialogue": "",
            "duration_sec": 12,
        },
    ]
}


MOCK_PUBLISH_OUTPUT = {
    "platforms": [
        {
            "name": "TikTok",
            "title": "The Box That Changed His Life",
            "caption": "He lost his job the same day he found the secret. Episode 1 out now. #shortdrama #revenge #fyp",
            "hashtags": ["#shortdrama", "#revenge", "#fyp", "#microdrama"],
            "best_time": "当地时间 19:30-21:00 发布（通勤后刷屏高峰，前 3 秒钩子完播率最优）",
            "notes": "标题埋悬念不加结局；封面取'门缝里的一只手'截图",
        },
        {
            "name": "YouTube Shorts",
            "title": "He Delivered His Last Order... To The Wrong Person",
            "caption": "The first 3 seconds decide everything. Full episode link in bio.",
            "hashtags": ["#shorts", "#drama", "#storytime"],
            "best_time": "当地时间 20:00 前后（Shorts 晚间推荐流量高）",
            "notes": "可承接长剧情延展，描述区放完整剧梗概",
        },
        {
            "name": "ReelShort",
            "title": "The Secret in the Delivery Box",
            "caption": "Falsely fired delivery rider stumbles onto evidence that can flip everything.",
            "hashtags": ["#urban", "#revenge"],
            "best_time": "平台审核 7-10 个工作日，建议工作日提交",
            "notes": "投稿需附剧名+一句话梗概+分镜脚本，切忌抄袭",
        },
    ],
    "compliance_checklist": [
        "背景音乐与音效需商用授权（Epidemic Sound/Artlist 等）",
        "演员肖像授权与 AI 配音使用声明",
        "字幕人工校对（人名/数字/敏感词）",
        "核实无真实地名、国旗与政治元素",
        "未成年人相关镜头审查",
    ],
    "resolution_note": "建议 1080x1920 / H.264 / 音频 48kHz；导出前确认字幕安全区",
}


def _mock_translate(user_message: str) -> dict:
    """按输入行原样回填（保证契约正确），真实环境由 DeepSeek 输出本地化结果。"""
    try:
        payload = json.loads(user_message)
        lines = payload.get("lines", [])
    except (ValueError, AttributeError):
        lines = []
    return {
        "lines": [
            {"line_id": item.get("line_id", index + 1), "translated": item.get("text", "")}
            for index, item in enumerate(lines)
        ],
        "notes": ["示例数据（mock 桩）：真实环境将输出跨文化本地化台词与替换说明"],
        "compliance_flags": [],
    }


def mock_reply(route: ModelRoute, agent_type: str, user_message: str = ""):
    from app.services.llm.client import LLMReply

    if agent_type == "translate":
        content = json.dumps(_mock_translate(user_message), ensure_ascii=False)
        prompt_tokens, completion_tokens = 220, 240
    elif agent_type == "publish":
        content = json.dumps(MOCK_PUBLISH_OUTPUT, ensure_ascii=False)
        prompt_tokens, completion_tokens = 180, 420
    elif agent_type == "storyboard":
        content = json.dumps(MOCK_STORYBOARD_OUTPUT, ensure_ascii=False)
        prompt_tokens, completion_tokens = 96, 288
    else:
        content = json.dumps(MOCK_SCRIPT_OUTPUT, ensure_ascii=False)
        prompt_tokens, completion_tokens = 128, 396
    return LLMReply(
        content=content,
        usage={
            "provider": "mock",
            "model": route.model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        },
    )
