from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Metal Max Wiki API"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://metalmax:metalmax@localhost:5432/metalmax"
    data_dir: Path = Path(__file__).resolve().parents[5] / "data"
    client_origin: str = "http://localhost:3000"
    session_cookie_name: str = "mm_session"
    session_days: int = Field(default=7, ge=1, le=30)
    ai_base_url: str = "http://127.0.0.1:11434/v1"
    ai_model: str = ""
    ai_api_key: SecretStr = SecretStr("")
    ai_timeout_seconds: float = Field(default=120, gt=0, le=300)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
