from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE = ROOT_DIR / ".env"


class Settings(BaseSettings):
    """W1 地基：所有配置从 .env / 环境变量读取，不在代码里写死。"""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    APP_ENV: str
    DATABASE_URL: str
    PGVECTOR_DATABASE_URL: str = ""
    LANGGRAPH_CHECKPOINT_URL: str = ""
    REDIS_URL: str
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int

    # LLM（W3+ Supervisor / Agent）
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL: str = "deepseek-chat"
    AGENT_ROUTER_TEMPERATURE: float = 0.0
    AGENT_FAQ_TEMPERATURE: float = 0.3
    FAQ_MIN_RELEVANCE_SCORE: float = 0.35

    # LangGraph Checkpoint（W3 Day 5）：postgres | memory
    AGENT_CHECKPOINT_BACKEND: str = "postgres"


settings = Settings()
