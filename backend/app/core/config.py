"""应用配置。

密钥规约：LLM_API_KEY 等敏感项不写进本文件与仓库，
统一由项目外 secrets 文件通过环境变量注入（见 README 开发规约）。
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


_DEV_JWT_SECRET = "opc-dev-secret-change-me-in-production-2026"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "OPC短剧出海AI集合智能体平台"
    debug: bool = False

    # 运行环境：dev（本地/测试）| prod（docker compose 生产编排置 OPC_ENV=prod）
    opc_env: str = "dev"

    # 数据库：开发 sqlite，生产 mysql
    database_url: str = "sqlite+aiosqlite:///./dev.db"

    # Redis（arq 任务队列；DB1 与其他项目隔离）
    redis_url: str = "redis://127.0.0.1:6379/1"

    # JWT（开发默认值仅限本地；OPC_ENV=prod 时使用默认值会拒绝启动）
    jwt_secret: str = _DEV_JWT_SECRET
    jwt_access_expire_minutes: int = 120
    jwt_refresh_expire_days: int = 7

    # CORS：逗号分隔来源；dev 默认 *（vite 5173 → 8000），
    # prod 默认关闭跨域（nginx 同源反代，无需跨域）
    cors_origins: str = ""

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

    # 上传限制（服务端兜底；nginx client_max_body_size 是第一道）
    upload_max_mb: int = 100
    # 逗号分隔的扩展名白名单；空 = 不限制（不建议）
    upload_allowed_ext: str = (
        "png,jpg,jpeg,webp,gif,mp3,wav,m4a,ogg,mp4,mov,webm,json,srt,vtt,txt"
    )

    def model_post_init(self, __context) -> None:
        """生产环境（OPC_ENV=prod）安全红线：弱 JWT 密钥直接拒绝启动。

        默认密钥公开在仓库里，忘改 = 任何人可伪造 token；
        宁可启动失败给出明确指引，也不带病上线。
        """
        if self.opc_env == "prod" and self.jwt_secret == _DEV_JWT_SECRET:
            raise RuntimeError(
                "生产环境（OPC_ENV=prod）禁止使用开发默认 JWT_SECRET："
                "请在 .env 注入强随机密钥（如 openssl rand -hex 32 生成）后重启"
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
