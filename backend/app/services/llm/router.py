"""模型路由与成本估算。

路由表按 agent_type 选择 (model, temperature, max_tokens)；
模型名可被环境变量 LLM_MODEL_<AGENT> 覆盖，未覆盖则用 LLM_MODEL_DEFAULT。

模型名与价格核价说明（2026-10-16 联网核实，api-docs.deepseek.com）：
- deepseek-chat / deepseek-reasoner 官方已弃用（2026-07-24），兼容映射到
  deepseek-v4-flash（非思考 / 思考模式）；新代码直接用 deepseek-v4-flash；
- 实测（2026-10-16）两者均返回 model=deepseek-flash，价格同 flash；
- 价格表单位「元 / 百万 tokens」，按官方 USD 价 × 7.1 折算（估算用）。
"""
from dataclasses import dataclass, replace

from app.core.config import get_settings


@dataclass(frozen=True)
class ModelRoute:
    model: str
    temperature: float
    max_tokens: int


DEFAULT_ROUTES: dict[str, ModelRoute] = {
    # script/storyboard/translate 输出体积大，max_tokens 拉满防截断；
    # 截断的 JSON 会被修复重试救场但会浪费一轮调用。
    "script": ModelRoute("deepseek-v4-flash", 0.8, 8192),
    "storyboard": ModelRoute("deepseek-v4-flash", 0.7, 8192),
    "translate": ModelRoute("deepseek-v4-flash", 0.3, 8192),
    "publish": ModelRoute("deepseek-v4-flash", 0.4, 2048),
    "analyze": ModelRoute("deepseek-v4-flash", 0.2, 2048),
    "optimize": ModelRoute("deepseek-v4-flash", 0.5, 2048),
    "match": ModelRoute("deepseek-v4-flash", 0.2, 2048),
}

_FALLBACK = ModelRoute("deepseek-v4-flash", 0.7, 2048)

# 元 / 百万 tokens（估算用；官方 USD 价 × 7.1，核价 2026-10-16）
# flash：$0.14 输入(cache miss) / $0.28 输出；pro：$0.435 / $0.87
PRICES_PER_MILLION: dict[str, dict[str, float]] = {
    "deepseek-v4-flash": {"input": 1.0, "output": 2.0},
    "deepseek-flash": {"input": 1.0, "output": 2.0},  # 响应侧实际模型名
    "deepseek-chat": {"input": 1.0, "output": 2.0},  # 已弃用别名 → 映射 flash
    "deepseek-reasoner": {"input": 1.0, "output": 2.0},  # 已弃用别名 → flash 思考模式
    "deepseek-v4-pro": {"input": 3.1, "output": 6.2},
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
