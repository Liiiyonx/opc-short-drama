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


def mock_reply(route: ModelRoute, agent_type: str):
    from app.services.llm.client import LLMReply

    if agent_type == "storyboard":
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
