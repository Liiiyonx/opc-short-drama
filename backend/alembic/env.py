"""Alembic 异步环境。

数据库 URL 从 app 配置注入（DATABASE_URL 环境变量），
不写在 alembic.ini 里；离线模式 P0 不使用。
"""
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config

import app.models  # noqa: F401  确保全部模型注册进 Base.metadata
from app.core.config import get_settings
from app.db.base import Base

config = context.config
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def do_run_migrations(connection) -> None:
    # 注意：autogenerate 对自定义 JSONType 只生成引用不生成 import，
    # 每次 autogenerate 后需检查迁移文件并手动补 `from app.db.types import JSONType`。
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,  # SQLite batch 迁移必需
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    raise SystemExit("P0 未配置离线模式，请使用：alembic upgrade head")
else:
    asyncio.run(run_async_migrations())
