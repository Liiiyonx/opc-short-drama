"""内存限流：登录失败防爆破（单进程部署形态的已知边界）。

滑动窗口计数，**只计失败尝试**（成功登录即清零该键）——
正确使用不受影响，暴力破解在连续失败 10 次后被锁 5 分钟。
多进程/多实例部署时应切换 Redis 实现（本项目的部署形态是单 VPS 单进程）。
"""
import time
from collections import defaultdict

from fastapi import HTTPException

_WINDOW_SECONDS = 300
_MAX_FAILURES = 10

_buckets: dict[str, list[float]] = defaultdict(list)


def login_key(username: str, ip: str) -> str:
    return f"{username}|{ip}"


def check_login_allowed(key: str) -> None:
    now = time.monotonic()
    bucket = _buckets.get(key)
    if not bucket:
        return
    recent = [t for t in bucket if now - t < _WINDOW_SECONDS]
    if recent:
        _buckets[key] = recent
    else:
        _buckets.pop(key, None)
        return
    if len(recent) >= _MAX_FAILURES:
        wait_min = int((_WINDOW_SECONDS - (now - recent[0])) // 60) + 1
        raise HTTPException(
            status_code=429,
            detail={
                "code": 42902,
                "message": f"失败次数过多，账号已临时锁定（约 {wait_min} 分钟后可再试）",
            },
        )


def record_login_failure(key: str) -> None:
    _buckets[key].append(time.monotonic())


def record_login_success(key: str) -> None:
    _buckets.pop(key, None)
