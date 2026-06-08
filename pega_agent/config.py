from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"

    linkedin_email: str | None = None
    linkedin_password: str | None = None
    getonboard_token: str | None = None
    newsapi_key: str | None = None

    pega_db_path: Path = Field(default=ROOT / "data" / "pega.sqlite")
    pega_human_in_the_loop: bool = True
    pega_default_locale: str = "es-CL"


settings = Settings()
