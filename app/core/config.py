from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="AI_CAREER_AGENT_",
        extra="ignore",
    )

    app_name: str = "AI Career Agent"
    environment: str = "local"
    debug: bool = False
    log_level: str = "INFO"
    database_url: str = (
        "postgresql+asyncpg://ai_career_agent:change-me@localhost:5432/ai_career_agent"
    )
    document_storage_dir: Path = Path("uploads")
    max_upload_size_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    embedding_provider: str = "deterministic"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = Field(default=256, gt=0)
    openai_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
