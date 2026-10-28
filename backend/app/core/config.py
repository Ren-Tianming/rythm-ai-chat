from functools import lru_cache
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "RyThM Chatbot"
    environment: Literal["development", "test", "production"] = "development"
    app_secret: str = "development-only-change-me"
    api_v1_prefix: str = "/api/v1"
    frontend_url: str = "http://localhost:5173"
    database_url: str = "postgresql+asyncpg://rythm:rythm@db:5432/rythm_chatbot"

    session_cookie_name: str = "rythm_session"
    csrf_cookie_name: str = "rythm_csrf"
    session_idle_hours: int = 24
    session_absolute_days: int = 14
    cookie_secure: bool = False

    max_input_chars: int = Field(default=4000, ge=1, le=16000)
    max_context_chars: int = Field(default=16000, ge=4000, le=100000)
    max_output_tokens: int | None = Field(default=None, ge=1)
    context_rounds: int = Field(default=5, ge=1, le=5)
    daily_chat_limit: int = Field(default=50, ge=1, le=10000)
    chat_per_minute_limit: int = Field(default=5, ge=1, le=100)
    max_concurrent_generations_per_user: int = Field(default=1, ge=1, le=10)
    generation_timeout_seconds: float = Field(default=600.0, ge=30.0, le=1800.0)
    provider_timeout_seconds: float = 120.0
    system_prompt: str = (
        "You are RyThM Chatbot, an accurate multilingual assistant. Match the depth requested by the user. "
        "Reply in the user's language unless asked otherwise."
    )

    # Optional global cost cap; unset means use the model's configured budget.
    upload_dir: str = "/app/uploads"
    document_max_bytes: int = Field(default=10 * 1024 * 1024, ge=1)
    document_batch_limit: int = Field(default=5, ge=1, le=20)
    document_user_limit: int = Field(default=50, ge=1)
    document_user_bytes: int = Field(default=100 * 1024 * 1024, ge=1)
    document_pdf_pages: int = Field(default=100, ge=1, le=1000)
    document_max_chars: int = Field(default=1000000, ge=1000)
    document_parse_timeout: int = Field(default=180, ge=10, le=600)
    ocr_languages: str = "jpn+chi_sim+eng"
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_version: str = "text-embedding-3-small-v1"
    embedding_dimensions: int = Field(default=1536, ge=1, le=4096)
    embedding_price_per_million: float = Field(default=0.02, ge=0)
    rag_top_k: int = Field(default=6, ge=5, le=8)
    rag_min_similarity: float = Field(default=0.25, ge=-1, le=1)
    rag_context_tokens: int = Field(default=6000, ge=1000, le=16000)
    chunk_tokens: int = Field(default=650, ge=500, le=800)
    chunk_overlap_tokens: int = Field(default=80, ge=0, le=150)

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = ""
    gemini_api_key: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_model: str = ""
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = ""

    turnstile_secret_key: str = ""
    turnstile_required: bool = False
    terms_version: str = "2026-07-29"

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = "noreply@example.com"
    smtp_use_tls: bool = True
    log_level: str = "INFO"

    # Accept the comma-separated value used by .env.example. NoDecode prevents
    # pydantic-settings from requiring JSON before our validator can split it.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )
    trusted_hosts: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "testserver"]
    )
    csrf_trusted_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )

    @field_validator("cors_origins", "trusted_hosts", "csrf_trusted_origins", mode="before")
    @classmethod
    def parse_csv(cls, value: object) -> object:
        if isinstance(value, str) and not value.startswith("["):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("Unsupported LOG_LEVEL")
        return normalized

    @model_validator(mode="after")
    def validate_production_safety(self) -> "Settings":
        if not self.is_production:
            return self
        errors: list[str] = []
        if len(self.app_secret) < 32 or self.app_secret == "development-only-change-me":
            errors.append("APP_SECRET must be a unique value of at least 32 characters")
        if not self.cookie_secure:
            errors.append("COOKIE_SECURE must be true")
        if urlparse(self.frontend_url).scheme != "https":
            errors.append("FRONTEND_URL must use https")
        if not self.turnstile_required or not self.turnstile_secret_key:
            errors.append("Turnstile must be required and configured")
        if not self.smtp_host:
            errors.append("SMTP_HOST must be configured")
        if not self.database_url or "rythm:rythm@" in self.database_url:
            errors.append("DATABASE_URL must use production credentials")
        if "*" in self.trusted_hosts:
            errors.append("TRUSTED_HOSTS must not contain a wildcard")
        providers = (
            (self.deepseek_api_key, self.deepseek_model),
            (self.gemini_api_key, self.gemini_model),
            (self.groq_api_key, self.groq_model),
        )
        if not any(key and model for key, model in providers):
            errors.append("At least one provider API key and model ID must be configured")
        if errors:
            raise ValueError("Unsafe production configuration: " + "; ".join(errors))
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def allowed_csrf_origins(self) -> set[str]:
        return {
            self.frontend_url.rstrip("/"),
            *(item.rstrip("/") for item in self.csrf_trusted_origins),
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
