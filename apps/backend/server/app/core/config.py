from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Metal Max Wiki API"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    database_url: str = "postgresql+psycopg://metalmax:metalmax@localhost:5432/metalmax"
    data_dir: Path = Path(__file__).resolve().parents[5] / "data"
    client_origin: str = "http://localhost:3000"
    session_cookie_name: str = "mm_session"
    session_days: int = Field(default=7, ge=1, le=30)
    ai_base_url: str = "http://127.0.0.1:11434/v1"
    ai_provider: Literal["openai-compatible", "ollama"] = "openai-compatible"
    ai_model: str = ""
    ai_api_key: SecretStr = SecretStr("")
    ai_timeout_seconds: float = Field(default=120, gt=0, le=300)
    ai_max_output_tokens: int = Field(default=4096, ge=128, le=32768)
    ai_max_context_chars: int = Field(default=4000, ge=4000, le=100000)
    ai_max_evidence_chunks: int = Field(default=12, ge=1, le=32)
    ai_ollama_context_tokens: int = Field(default=16384, ge=2048, le=131072)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
