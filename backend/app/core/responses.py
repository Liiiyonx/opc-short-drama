"""统一响应包裹：{code, message, data}（规范见 docs/04-API设计.md）。"""


def ok(data=None, message: str = "ok") -> dict:
    return {"code": 0, "message": message, "data": data}
