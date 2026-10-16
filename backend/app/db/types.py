"""跨数据库 JSON 列类型。

生产 MySQL 用原生 JSON 类型；开发 SQLite 用 TEXT + 应用层序列化。
对模型层透明：读写都是 Python dict/list。
"""
import json

from sqlalchemy import TEXT, JSON, Text, TypeDecorator


class JSONType(TypeDecorator):
    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "mysql":
            return dialect.type_descriptor(JSON)
        return dialect.type_descriptor(TEXT)

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return json.dumps(value, ensure_ascii=False)

    def process_result_value(self, value, dialect):
        if value is None or isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return None
