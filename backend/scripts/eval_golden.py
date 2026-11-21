"""黄金评测集运行器（docs/08 §7.2 质量评测）。

对 golden_cases.json 的 30 条固定样例逐条直调智能体（orchestrator 全链路：
契约校验 → 配额 → 会话 → 调用日志），产出契约通过率 / 延迟 / 分智能体报告。

- mock 模式（默认强制）：确定性运行，契约通过率应 100%，用于回归；
- 真实模型接入后：同一套样例跑质量与成本回归（LLM_PROVIDER=openai_compat）。

用法（backend/ 目录）：
    python -m scripts.eval_golden                 # 运行并写 backend/evals/report.json
    python -m scripts.eval_golden --strict        # 通过率 <100% 时退出码 1（CI 用）

验收口径（计划书 §7.3）：JSON 契约通过率 ≥ 99%；核心链路成功率 ≥ 99%。
"""
import argparse
import asyncio
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

os.environ["LLM_PROVIDER"] = "mock"
os.environ["TTS_PROVIDER"] = "mock"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:  # noqa: BLE001
    pass

from fastapi import HTTPException  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

import app.models  # noqa: F401,E402
from app.agents.orchestrator import invoke_agent  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.storage.factory import get_storage  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
EVALS_DIR = REPO_ROOT / "backend" / "evals"


async def _make_env(tmp: Path):
    """一次性评测环境：临时 SQLite + 评测学生账号（隔离于开发库）。"""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp}/eval.db", poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        user = User(
            username="eval_runner",
            password_hash=hash_password("eval123456"),
            role="student",
            status=1,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return engine, factory, user


async def run_eval(strict: bool) -> int:
    spec = json.loads((EVALS_DIR / "golden_cases.json").read_text(encoding="utf-8"))
    cases = spec["cases"]
    print(f"[eval] 黄金评测集 v{spec['version']}：{len(cases)} 条样例（mock 确定性）")

    with tempfile.TemporaryDirectory() as tmp_raw:
        tmp = Path(tmp_raw)
        os.environ["LOCAL_STORAGE_PATH"] = str(tmp / "storage")
        get_storage.cache_clear()
        engine, factory, user = await _make_env(tmp)

        results = []
        async with factory() as db:
            for case in cases:
                t0 = time.perf_counter()
                outcome, output, error = "ok", None, ""
                try:
                    output = await invoke_agent(
                        case["agent_type"], dict(case["input"]), user=user, db=db
                    )
                except HTTPException as exc:
                    outcome = f"http{exc.status_code}"
                    error = str(exc.detail)[:120] if isinstance(exc.detail, dict) else str(exc.detail)[:120]
                except Exception as exc:  # noqa: BLE001
                    outcome = "error"
                    error = f"{type(exc).__name__}: {exc}"[:120]
                latency_ms = round((time.perf_counter() - t0) * 1000, 1)

                want = case["expected_outcome"]
                if want == "ok":
                    # invoke_agent 返回 {session_id, agent_type, result, usage}；产物在 result 键下
                    payload = output.get("result") if isinstance(output, dict) else None
                    missing = [k for k in case.get("expected_keys", []) if not isinstance(payload, dict) or k not in payload]
                    passed = outcome == "ok" and not missing
                    if missing:
                        error = f"输出缺字段: {missing}"
                else:  # reject：契约闸门必须拦下（422）
                    passed = outcome == "http422"
                    if not passed:
                        error = f"期望契约拒绝(422)，实际 {outcome}"

                results.append({
                    "id": case["id"],
                    "agent_type": case["agent_type"],
                    "category": case["category"],
                    "market": case.get("market", "—"),
                    "pass": passed,
                    "latency_ms": latency_ms,
                    "outcome": outcome if want == "reject" else "ok",
                    "error": error,
                })
                mark = "PASS" if passed else "FAIL"
                print(f"  [{mark}] {case['id']} ({case['agent_type']}/{case['category']}) {latency_ms}ms"
                      + (f" —— {error}" if error else ""))
        await engine.dispose()

    # ---------- 汇总报告 ----------
    total = len(results)
    passed = sum(1 for r in results if r["pass"])
    latencies = sorted(r["latency_ms"] for r in results)

    def p(q: float) -> float:
        return latencies[min(len(latencies) - 1, int(len(latencies) * q))]

    by_agent: dict[str, dict] = {}
    for r in results:
        bucket = by_agent.setdefault(r["agent_type"], {"total": 0, "pass": 0, "latencies": []})
        bucket["total"] += 1
        bucket["pass"] += r["pass"]
        bucket["latencies"].append(r["latency_ms"])

    report = {
        "eval_set_version": spec["version"],
        "mode": "mock(deterministic)" if os.environ.get("LLM_PROVIDER") == "mock" else "real",
        "total": total,
        "passed": passed,
        "contract_pass_rate": round(passed / total * 100, 2),
        "latency_p50_ms": p(0.50),
        "latency_p95_ms": p(0.95),
        "by_agent": {
            k: {
                "total": v["total"],
                "pass": v["pass"],
                "pass_rate": round(v["pass"] / v["total"] * 100, 1),
                "latency_p95_ms": sorted(v["latencies"])[min(len(v["latencies"]) - 1, int(len(v["latencies"]) * 0.95))],
            }
            for k, v in by_agent.items()
        },
        "failures": [r for r in results if not r["pass"]],
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    (EVALS_DIR / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print(f"========== 评测结果：{passed}/{total} ｜ 契约通过率 {report['contract_pass_rate']}% "
          f"｜ P50 {report['latency_p50_ms']}ms ｜ P95 {report['latency_p95_ms']}ms ==========")
    for agent, stats in report["by_agent"].items():
        print(f"  {agent:<12} {stats['pass']}/{stats['total']}  P95 {stats['latency_p95_ms']}ms")
    for f in report["failures"]:
        print(f"  [FAIL] {f['id']}: {f['error']}")

    if strict and report["contract_pass_rate"] < 99:
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser(description="黄金评测集运行器")
    parser.add_argument("--strict", action="store_true", help="通过率 <99%% 时退出码 1")
    args = parser.parse_args()
    sys.exit(asyncio.run(run_eval(args.strict)))


if __name__ == "__main__":
    main()
