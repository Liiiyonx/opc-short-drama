"""非 AI 接口响应基准（DoD #5「P95 < 500ms」的本地初测）。

用法（backend/ 目录，需 API 已启动；建议先跑 bash demo_up.sh）：
    python -m scripts.bench_api                        # 默认 127.0.0.1:8000，每接口 50 次
    python -m scripts.bench_api --n 100 --base http://127.0.0.1:8000

输出各接口 P50/P95/P99（毫秒）与达标判定（P95 < 500ms）。
"""
import argparse
import statistics
import time

import httpx


def login(base: str, username: str, password: str) -> str:
    resp = httpx.post(
        f"{base}/api/v1/auth/login",
        json={"username": username, "password": password},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["data"]["access_token"]


def measure(client: httpx.Client, url: str, headers: dict, n: int) -> list[float]:
    samples: list[float] = []
    for _ in range(n):
        started = time.perf_counter()
        resp = client.get(url, headers=headers)
        elapsed = (time.perf_counter() - started) * 1000
        if resp.status_code >= 400:
            raise RuntimeError(f"{url} -> HTTP {resp.status_code}: {resp.text[:120]}")
        samples.append(elapsed)
    return samples


def summarize(name: str, samples: list[float]) -> tuple[str, float]:
    samples_sorted = sorted(samples)

    def pct(p: float) -> float:
        index = min(len(samples_sorted) - 1, int(len(samples_sorted) * p))
        return samples_sorted[index]

    p50, p95, p99 = pct(0.50), pct(0.95), pct(0.99)
    verdict = "PASS" if p95 < 500 else "SLOW"
    icon = "✓" if verdict == "PASS" else "!"
    print(
        f"  {icon} {name:<38} P50 {p50:7.1f}ms · P95 {p95:7.1f}ms · P99 {p99:7.1f}ms"
    )
    return verdict, p95


def main() -> None:
    parser = argparse.ArgumentParser(description="OPC 非 AI 接口基准")
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--n", type=int, default=50, help="每接口请求次数")
    parser.add_argument("--user", default="student01")
    parser.add_argument("--password", default="student123")
    args = parser.parse_args()

    base = args.base.rstrip("/")
    print(f"\n=== 接口基准：{base} · 每接口 {args.n} 次 ===\n")

    token = login(base, args.user, args.password)
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=15) as client:
        works = client.get(f"{base}/api/v1/works?page=1&page_size=20", headers=headers)
        works.raise_for_status()
        items = works.json()["data"]["items"]
        first_work = items[0]["id"] if items else None

        targets = [
            ("GET /health", f"{base}/health", {}),
            ("GET /works（列表 20 条）", f"{base}/api/v1/works?page=1&page_size=20", headers),
            ("GET /tasks（教学任务）", f"{base}/api/v1/tasks", headers),
            ("GET /orders（工单）", f"{base}/api/v1/orders", headers),
            ("GET /courses", f"{base}/api/v1/courses", headers),
        ]
        if first_work is not None:
            targets.append(
                (f"GET /works/{first_work}（详情+资产）", f"{base}/api/v1/works/{first_work}", headers)
            )

        verdicts = []
        for name, url, hdrs in targets:
            samples = measure(client, url, hdrs, args.n)
            verdict, _ = summarize(name, samples)
            verdicts.append(verdict)

    passed = verdicts.count("PASS")
    print(f"\n判定：{passed}/{len(verdicts)} 接口 P95 < 500ms")
    if passed == len(verdicts):
        print("DoD #5（非 AI 接口 P95 < 500ms）本机初测通过 ✓")
    else:
        print("存在超时接口，部署后请复测并排查（SQLite/冷启动/索引）。")


if __name__ == "__main__":
    main()
