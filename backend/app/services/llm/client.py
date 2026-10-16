"""LLM 网关客户端（OpenAI 兼容协议）。

规则（项目铁律）：
- 默认走云端 DeepSeek；无密钥时抛 LLMNotConfigured，消息引导用户
  到项目外 secrets 文件取密钥，绝不静默回退本地 Ollama；
- LLM_PROVIDER=mock 是显式启用的测试桩（无密钥联调用），不是回退路径；
- 所有调用由上层编排器落 agent_call_logs（token / 耗时 / 成本估算）。
"""
import asyncio
import json
import re
from dataclasses import dataclass, field

import httpx

from app.core.config import get_settings
from app.services.llm.router import route_model

NO_KEY_MESSAGE = (
    "未配置 LLM_API_KEY。请维护项目外密钥文件 D:\\VeriCall_data\\secrets\\opc_secrets.env，"
    "在 bash 中执行 set -a; source <文件>; set +a 后重启服务"
)


class LLMError(Exception):
    """LLM 网关错误基类。"""


class LLMNotConfigured(LLMError):
    """未配置密钥（明确报错，不静默回退）。"""


class LLMUpstreamError(LLMError):
    """上游不可用 / 返回异常。"""


@dataclass
class LLMReply:
    content: str
    usage: dict = field(default_factory=dict)  # provider/model/prompt_tokens/completion_tokens


def extract_json(text: str) -> dict:
    """从模型输出中提取 JSON：容忍 ```json 包裹与前后多余文字。"""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        raise LLMError("模型未返回合法 JSON，无法解析产物")


async def chat_completion(
    system: str,
    user: str,
    agent_type: str,
    *,
    json_mode: bool = True,
) -> LLMReply:
    settings = get_settings()
    route = route_model(agent_type)

    if settings.llm_provider == "mock":
        from app.services.llm.mock import mock_reply

        return mock_reply(route)

    if not settings.llm_api_key:
        raise LLMNotConfigured(NO_KEY_MESSAGE)

    url = settings.llm_base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
    body: dict = {
        "model": route.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": route.temperature,
        "max_tokens": route.max_tokens,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    last_error: Exception | None = None
    for attempt in range(settings.llm_max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
                response = await client.post(url, json=body, headers=headers)
            if response.status_code != 200:
                raise LLMUpstreamError(
                    f"LLM 上游返回 HTTP {response.status_code}: {response.text[:200]}"
                )
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage") or {}
            return LLMReply(
                content=content,
                usage={
                    "provider": "openai_compat",
                    "model": route.model,
                    "prompt_tokens": int(usage.get("prompt_tokens", 0)),
                    "completion_tokens": int(usage.get("completion_tokens", 0)),
                },
            )
        except (httpx.HTTPError, LLMUpstreamError, KeyError, ValueError) as exc:
            last_error = exc
            if attempt < settings.llm_max_retries:
                await asyncio.sleep(1.5 * (attempt + 1))
    raise LLMUpstreamError(f"LLM 调用失败（重试 {settings.llm_max_retries} 次后）：{last_error}")
