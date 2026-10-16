"""环境自检：部署 / 本地实测 / 演示前，一条命令验证全部依赖与链路。

用法（backend/ 目录）：
    python -m scripts.selfcheck                # 全检（含真实 LLM 与 Edge-TTS 调用）
    python -m scripts.selfcheck --skip-external  # 跳过真实外部调用（省费用/离线）

检查项：
  1. Python 版本与关键依赖        5. LLM 密钥配置
  2. ffmpeg / ffprobe            6. LLM 真实调用（1 次极小请求）
  3. Redis 连通                  7. Edge-TTS 真实合成（关键：验证真实配音可用）
  4. 数据库与迁移                8. 本地存储可写

退出码：0 = 全部通过（或仅警告）；1 = 存在失败项。
"""
import argparse
import asyncio
import sys
import time
from pathlib import Path

PASS, FAIL, WARN = "PASS", "FAIL", "WARN"
results: list[tuple[str, str, str]] = []  # (状态, 项目, 说明)


def record(status: str, item: str, detail: str) -> None:
    icon = {PASS: "✓", FAIL: "✗", WARN: "!"}[status]
    color = {PASS: "\033[32m", FAIL: "\033[31m", WARN: "\033[33m"}[status]
    print(f"  {color}{icon}\033[0m {item:<28} {detail}")
    results.append((status, item, detail))


def check_python_and_deps() -> None:
    py = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 11):
        record(PASS, "Python 版本", py)
    else:
        record(WARN, "Python 版本", f"{py}（建议 3.11+）")
    missing = []
    for name in ["fastapi", "sqlalchemy", "alembic", "httpx", "pydantic", "arq", "redis", "edge_tts"]:
        try:
            __import__(name)
        except ImportError:
            missing.append(name)
    if missing:
        record(FAIL, "Python 依赖", f"缺少：{', '.join(missing)}（pip install -r requirements.txt）")
    else:
        record(PASS, "Python 依赖", "fastapi/sqlalchemy/alembic/httpx/arq/redis/edge_tts 齐全")


def check_ffmpeg() -> None:
    import subprocess

    for bin_name in ["ffmpeg", "ffprobe"]:
        try:
            proc = subprocess.run(
                [bin_name, "-version"], capture_output=True, timeout=10
            )
            version = proc.stdout.decode("utf-8", "ignore").splitlines()[0][:60]
            record(PASS, bin_name, version)
        except FileNotFoundError:
            record(FAIL, bin_name, "未安装（部署机：apt install ffmpeg / Windows 下载并加 PATH）")
        except Exception as exc:  # noqa: BLE001
            record(FAIL, bin_name, str(exc)[:80])


def check_redis() -> None:
    from app.core.config import get_settings

    url = get_settings().redis_url
    try:
        import redis

        client = redis.Redis.from_url(url, socket_timeout=3, protocol=2)
        pong = client.ping()
        info = client.info("server")
        version = info.get("redis_version", "?")
        if pong:
            note = f"{version}" + ("（较老版本，仅 RESP2，已兼容）" if version < "4" else "")
            record(PASS, "Redis 连通", f"{url} · {note}")
    except Exception as exc:  # noqa: BLE001
        record(FAIL, "Redis 连通", f"{url} · {str(exc)[:80]}（异步任务需要 Redis）")


def check_database() -> None:
    try:
        import sqlite3

        from app.core.config import get_settings

        url = get_settings().database_url
        if "sqlite" in url:
            db_path = url.split("///")[-1]
            path = Path(db_path)
            if not path.exists():
                record(WARN, "数据库", f"{db_path} 不存在（先跑 python -m alembic upgrade head）")
                return
            conn = sqlite3.connect(db_path)
            tables = conn.execute(
                "select count(*) from sqlite_master where type='table' and name not like 'sqlite_%'"
            ).fetchone()[0]
            ver = conn.execute("select version_num from alembic_version").fetchone()
            conn.close()
            record(PASS, "数据库", f"SQLite · {tables} 张表 · 迁移版本 {ver[0][:12] if ver else '?'}")
        else:
            record(WARN, "数据库", f"{url.split('://')[0]}（跳过深度检查，请自行确认连通）")
    except Exception as exc:  # noqa: BLE001
        record(FAIL, "数据库", str(exc)[:100])


def check_secrets() -> None:
    from app.core.config import get_settings

    settings = get_settings()
    if settings.llm_api_key:
        hint = "（来自环境变量，密钥不回显）"
        record(PASS, "LLM 密钥", f"已配置 · base={settings.llm_base_url} · model={settings.llm_model_default} {hint}")
    else:
        record(
            WARN,
            "LLM 密钥",
            "未配置 → 将只能以 LLM_PROVIDER=mock 演示；"
            "配置方法：set -a; source D:\\VeriCall_data\\secrets\\opc_secrets.env; set +a",
        )


async def check_llm_live() -> None:
    from app.core.config import get_settings

    settings = get_settings()
    if settings.llm_provider == "mock":
        record(WARN, "LLM 真实调用", "当前 LLM_PROVIDER=mock，跳过（真实演示请用 openai_compat）")
        return
    if not settings.llm_api_key:
        record(WARN, "LLM 真实调用", "无密钥，跳过")
        return
    try:
        import httpx

        started = time.perf_counter()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                settings.llm_base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                json={
                    "model": settings.llm_model_default,
                    "messages": [{"role": "user", "content": "回复：OK"}],
                    "max_tokens": 5,
                },
            )
        elapsed = int((time.perf_counter() - started) * 1000)
        if resp.status_code == 200:
            model = resp.json().get("model", "?")
            record(PASS, "LLM 真实调用", f"{model} · {elapsed}ms")
        else:
            record(FAIL, "LLM 真实调用", f"HTTP {resp.status_code}: {resp.text[:100]}")
    except Exception as exc:  # noqa: BLE001
        record(FAIL, "LLM 真实调用", str(exc)[:120])


def check_tts_live() -> None:
    """Edge-TTS 真实合成（关键检查：演示前必须全绿）。"""
    try:
        import asyncio as aio

        from app.services.tts.base import TTSResult  # noqa: F401
        from app.services.tts.edge_provider import EdgeTTSProvider

        async def run() -> None:
            provider = EdgeTTSProvider(max_attempts=2)
            started = time.perf_counter()
            result = await provider.synthesize("你好，这是语音自检。", "zh-CN-XiaoxiaoNeural")
            elapsed = int((time.perf_counter() - started) * 1000)
            if result.audio and result.duration_ms > 0:
                record(
                    PASS,
                    "Edge-TTS 真实合成",
                    f"{len(result.audio) / 1024:.1f} KB · {result.duration_ms}ms 音频 · 用时 {elapsed}ms",
                )
            else:
                record(FAIL, "Edge-TTS 真实合成", "返回空音频")

        aio.run(run())
    except Exception as exc:  # noqa: BLE001
        message = str(exc)[:140]
        hint = ""
        if "403" in message or "Handshake" in message or "connect" in message.lower():
            hint = "（当前网络无法访问微软语音服务；请检查网络/代理，或演示改用 TTS_PROVIDER=mock）"
        record(FAIL, "Edge-TTS 真实合成", message + hint)


def check_storage() -> None:
    try:
        from app.services.storage.factory import get_storage

        storage = get_storage()
        key = storage.put("_selfcheck/probe.txt", b"ok", "text/plain")
        data = storage.get_bytes(key)
        assert data == b"ok"
        record(PASS, "本地存储", f"读写正常（backend={type(storage).__name__}）")
    except Exception as exc:  # noqa: BLE001
        record(FAIL, "本地存储", str(exc)[:100])


def main() -> None:
    parser = argparse.ArgumentParser(description="OPC 环境自检")
    parser.add_argument("--skip-external", action="store_true", help="跳过真实 LLM / TTS 调用")
    args = parser.parse_args()

    print("\n=== OPC 短剧出海平台 · 环境自检 ===\n")
    check_python_and_deps()
    check_ffmpeg()
    check_redis()
    check_database()
    check_secrets()
    check_storage()
    if not args.skip_external:
        asyncio.run(check_llm_live())
        check_tts_live()
    else:
        record(WARN, "真实外部调用", "已按 --skip-external 跳过（LLM / Edge-TTS）")

    failed = [item for status, item, _ in results if status == FAIL]
    warned = [item for status, item, _ in results if status == WARN]
    print(f"\n结果：{len(results) - len(failed) - len(warned)} 通过 / {len(warned)} 警告 / {len(failed)} 失败")
    if failed:
        print("失败项：" + "、".join(failed))
        print("提示：修复后重跑本脚本；仅警告不影响 mock 模式演示。")
        sys.exit(1)
    print("环境就绪 ✓" + ("（部分警告项见上）" if warned else ""))
    sys.exit(0)


if __name__ == "__main__":
    main()
