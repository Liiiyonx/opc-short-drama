"""LLM 网关客户端（OpenAI 兼容协议）。

规则（项目铁律）：
- 默认走云端 DeepSeek；无密钥时抛 LLMNotConfigured，消息引导用户
  到项目外 secrets 文件取密钥，绝不静默回退本地 Ollama；
- LLM_PROVIDER=mock 是显式启用的测试桩（无密钥联调用），不是回退路径；
- 所有调用由上层编排器落 agent_call_logs（token / 耗时 / 成本估算）。

健壮性：
- extract_json 容忍代码块包裹 / 前后杂文 / 尾随逗号 / 截断后首个完整对象；
- chat_json 在解析失败时自动发起一轮「修复重试」（把坏输出喂回要求重排
  JSON），usage 累计两次调用，避免已付费的生成因格式问题整单报废。
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

REPAIR_INSTRUCTION = (
    "你上一次的输出不是合法 JSON（可能缺失引号、括号不匹配、包含多余文字或被截断）。"
    "请把上次输出重新整理为**严格合法的 JSON**，结构必须与之前要求完全一致；"
    "只输出 JSON 本体，不要解释、不要 Markdown 代码块、不要多余字符。\n\n"
    "上次输出如下：\n"
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


def _strip_code_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def extract_json(text: str) -> dict:
    """从模型输出中提取 JSON（容错版）。

    依次尝试：直接解析 → 去代码块 → raw_decode 取首个完整对象 →
    去尾随逗号 → 贪婪正则兜底。全部失败才抛错。
    """
    cleaned = _strip_code_fence(text)
    candidates: list[str] = [cleaned]
    # 去除对象/数组内尾随逗号（常见的模型输出瑕疵）
    candidates.append(re.sub(r",\s*([}\]])", r"\1", cleaned))

    for candidate in candidates:
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
        # raw_decode：容忍 JSON 后面跟着解释文字
        start = candidate.find("{")
        if start != -1:
            try:
                data, _ = json.JSONDecoder().raw_decode(candidate[start:])
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                pass
    match = re.search(r"\{.*\}", cleaned, re.S)
    if match:
        try:
            return json.loads(re.sub(r",\s*([}\]])", r"\1", match.group(0)))
        except json.JSONDecodeError:
            pass
    raise LLMError("模型未返回合法 JSON，无法解析产物")


# ---------- HTTP 连接复用（按事件循环缓存，省 TLS 握手） ----------

_clients: dict[int, httpx.AsyncClient] = {}


def _get_client(timeout: float) -> httpx.AsyncClient:
    loop = asyncio.get_running_loop()
    key = id(loop)
    client = _clients.get(key)
    if client is None or client.is_closed:
        client = httpx.AsyncClient(
            timeout=timeout,
            limits=httpx.Limits(max_connections=16, max_keepalive_connections=8),
        )
        _clients[key] = client
    return client


async def close_clients() -> None:
    """优雅关闭（测试/进程退出用；不影响线上常驻进程复用）。"""
    for key, client in list(_clients.items()):
        try:
            await client.aclose()
        except Exception:  # noqa: BLE001
            pass
        _clients.pop(key, None)


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

        return mock_reply(route, agent_type, user)

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
            client = _get_client(settings.llm_timeout_seconds)
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


async def chat_json(
    system: str, user: str, agent_type: str
) -> tuple[dict, dict]:
    """调用 LLM 并返回 (解析后的 JSON, 累计 usage)。

    解析失败时自动发起一轮修复重试；usage 累计所有轮次
    （token / 成本按实际消耗记账）。
    """
    reply = await chat_completion(system=system, user=user, agent_type=agent_type)
    usage = dict(reply.usage)
    try:
        return extract_json(reply.content), usage
    except LLMError:
        pass

    repair_user = (
        f"{REPAIR_INSTRUCTION}{reply.content[:8000]}"
    )
    repair = await chat_completion(system=system, user=repair_user, agent_type=agent_type)
    usage["prompt_tokens"] = int(usage.get("prompt_tokens", 0)) + int(
        repair.usage.get("prompt_tokens", 0)
    )
    usage["completion_tokens"] = int(usage.get("completion_tokens", 0)) + int(
        repair.usage.get("completion_tokens", 0)
    )
    usage["repair_roundtrip"] = True
    try:
        return extract_json(repair.content), usage
    except LLMError as exc:
        raise LLMError(f"JSON 解析失败且修复重试未成功：{exc}") from exc
