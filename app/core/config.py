from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
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
    openai_api_key: str | None = Field(default=None, repr=False)
    llm_provider: str = "fake"
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = Field(default=30, gt=0, allow_inf_nan=False)
    llm_max_output_tokens: int = Field(default=1024, gt=0)
    qa_max_context_chunks: int = Field(default=5, ge=1, le=20)

    @field_validator("llm_model")
    @classmethod
    def validate_llm_model(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("LLM_MODEL must not be empty")
        return value.strip()


@lru_cache
def get_settings() -> Settings:
    return Settings()
