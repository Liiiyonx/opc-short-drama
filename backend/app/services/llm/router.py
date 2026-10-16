"""模型路由与成本估算。

路由表按 agent_type 选择 (model, temperature, max_tokens)；
模型名可被环境变量 LLM_MODEL_<AGENT> 覆盖，未覆盖则用 LLM_MODEL_DEFAULT。
价格表为估算用，单位「元 / 百万 tokens」，以官网实时价格为准修改。
"""
from dataclasses import dataclass, replace

from app.core.config import get_settings


@dataclass(frozen=True)
class ModelRoute:
    model: str
    temperature: float
    max_tokens: int


DEFAULT_ROUTES: dict[str, ModelRoute] = {
    # script/storyboard 输出体积大（多集大纲/多镜头列表），max_tokens 拉满
    # 防截断；截断的 JSON 会被修复重试救场但会浪费一轮调用。
    "script": ModelRoute("deepseek-chat", 0.8, 8192),
    "storyboard": ModelRoute("deepseek-chat", 0.7, 8192),
    "translate": ModelRoute("deepseek-chat", 0.3, 4096),
    "analyze": ModelRoute("deepseek-chat", 0.2, 2048),
    "optimize": ModelRoute("deepseek-chat", 0.5, 2048),
    "match": ModelRoute("deepseek-chat", 0.2, 2048),
}

_FALLBACK = ModelRoute("deepseek-chat", 0.7, 2048)

# 元 / 百万 tokens（估算用）
PRICES_PER_MILLION: dict[str, dict[str, float]] = {
    "deepseek-chat": {"input": 2.0, "output": 8.0},
}


def route_model(agent_type: str) -> ModelRoute:
    settings = get_settings()
    base = DEFAULT_ROUTES.get(agent_type, _FALLBACK)
    override = {
        "script": settings.llm_model_script,
        "storyboard": settings.llm_model_storyboard,
        "translate": settings.llm_model_translate,
    }.get(agent_type)
    model = override or settings.llm_model_default
    return replace(base, model=model)


def estimate_cost_cny(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """单次调用成本估算（元）。未知模型按 0 计，避免虚报。"""
    price = PRICES_PER_MILLION.get(model)
    if not price:
        return 0.0
    cost = (
        prompt_tokens / 1_000_000 * price["input"]
        + completion_tokens / 1_000_000 * price["output"]
    )
    return round(cost, 6)
