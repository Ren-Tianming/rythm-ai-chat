from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "RyThM Chatbot"
    environment: Literal["development", "test", "production"] = "development"
    api_v1_prefix: str = "/api/v1"
    frontend_url: str = "http://localhost:5173"
    database_url: str = "postgresql+asyncpg://rythm:rythm@db:5432/rythm_chatbot"

    session_cookie_name: str = "rythm_session"
    csrf_cookie_name: str = "rythm_csrf"
    session_idle_hours: int = 24
    session_absolute_days: int = 14
    cookie_secure: bool = False

    max_input_chars: int = 4000
    max_output_tokens: int = 512
    context_rounds: int = 5
    daily_chat_limit: int = 50
    provider_timeout_seconds: float = 60.0
    system_prompt: str = (
        "You are RyThM Chatbot, a concise, accurate multilingual assistant. "
        "Reply in the user's language unless asked otherwise."
    )

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    gemini_api_key: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"

    turnstile_secret_key: str = ""
    turnstile_required: bool = False

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = "noreply@example.com"
    smtp_use_tls: bool = True

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: object) -> object:
        if isinstance(value, str) and not value.startswith("["):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
