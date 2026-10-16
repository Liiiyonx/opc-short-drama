"""应用配置。

密钥规约：LLM_API_KEY 等敏感项不写进本文件与仓库，
统一由项目外 secrets 文件通过环境变量注入（见 README 开发规约）。
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "OPC短剧出海AI集合智能体平台"
    debug: bool = False

    # 数据库：开发 sqlite，生产 mysql
    database_url: str = "sqlite+aiosqlite:///./dev.db"

    # Redis（arq 任务队列；DB1 与其他项目隔离）
    redis_url: str = "redis://127.0.0.1:6379/1"

    # JWT（开发默认值仅限本地；生产必须在环境变量注入强随机密钥）
    jwt_secret: str = "opc-dev-secret-change-me-in-production-2026"
    jwt_access_expire_minutes: int = 120
    jwt_refresh_expire_days: int = 7

    # LLM 多模型网关（OpenAI 兼容；默认云端 DeepSeek）
    llm_provider: str = "openai_compat"  # openai_compat | mock（mock 仅无密钥联调用，显式启用，非回退）
    llm_base_url: str = "https://api.deepseek.com"
    llm_api_key: str = ""
    # 2026-10 官方现役模型名（deepseek-chat 别名已弃用，兼容映射到 v4-flash）
    llm_model_default: str = "deepseek-v4-flash"
    llm_model_script: str = ""
    llm_model_storyboard: str = ""
    llm_model_translate: str = ""
    llm_timeout_seconds: int = 60
    llm_max_retries: int = 1

    # TTS
    tts_provider: str = "edge-tts"
    tts_concurrency: int = 4  # 配音逐行并行合成的并发上限
    # 异步任务卡死判定（秒）：worker 崩溃/未启动时，超时自动判失败
    agent_task_timeout_seconds: int = 1800

    # 对象存储：local / minio
    storage_backend: str = "local"
    local_storage_path: str = "./storage"
    minio_endpoint: str = "127.0.0.1:9000"
    minio_access_key: str = "opcadmin"
    minio_secret_key: str = "opcadmin123"
    minio_bucket: str = "opc"
    minio_secure: bool = False

    # 媒体合成
    ffmpeg_path: str = "ffmpeg"

    # 智能体配额
    quota_text_calls_per_user_day: int = 50
    quota_media_calls_per_user_day: int = 10


@lru_cache
def get_settings() -> Settings:
    return Settings()
