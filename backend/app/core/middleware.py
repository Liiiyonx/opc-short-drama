"""纯 ASGI 访问日志中间件（不走 BaseHTTPMiddleware，零包装开销）。

- 每个请求生成/透传 X-Request-ID，响应头回写，日志可串联前端报障；
- 记录 method/path/status/耗时（ms），跳过健康探针噪声；
- 4xx/5slow 标 warn，便于 grep 定位。
"""
import logging
import time
import uuid

logger = logging.getLogger("opc.access")

_SLOW_MS = 1000.0

# 编排层高频轮询的探针路径，不进访问日志
_QUIET_PATHS = {"/health", "/livez", "/readyz"}


class AccessLogMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        request_id = (
            headers.get(b"x-request-id", b"").decode("latin-1") or uuid.uuid4().hex[:12]
        )
        path = scope.get("path", "")
        method = scope.get("method", "")
        started = time.perf_counter()
        status_holder = {"status": 0}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                headers_list = list(message.get("headers") or [])
                headers_list.append((b"x-request-id", request_id.encode("latin-1")))
                message = {**message, "headers": headers_list}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            if path not in _QUIET_PATHS:
                duration_ms = (time.perf_counter() - started) * 1000
                status = status_holder["status"]
                level = (
                    logging.WARNING
                    if (status >= 400 or duration_ms > _SLOW_MS)
                    else logging.INFO
                )
                logger.log(
                    level,
                    '%s %s -> %s %.1fms rid=%s',
                    method,
                    path,
                    status,
                    duration_ms,
                    request_id,
                )
