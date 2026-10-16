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


def mock_reply(route: ModelRoute):
    from app.services.llm.client import LLMReply

    content = json.dumps(MOCK_SCRIPT_OUTPUT, ensure_ascii=False)
    return LLMReply(
        content=content,
        usage={
            "provider": "mock",
            "model": route.model,
            "prompt_tokens": 128,
            "completion_tokens": 396,
        },
    )
