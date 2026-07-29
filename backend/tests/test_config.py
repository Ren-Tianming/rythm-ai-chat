from app.core.config import Settings
from pydantic import ValidationError


def test_cors_origins_accepts_comma_separated_environment_value(monkeypatch):
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "http://localhost:5173, https://chat.example.com",
    )

    settings = Settings(_env_file=None)

    assert settings.cors_origins == [
        "http://localhost:5173",
        "https://chat.example.com",
    ]


def test_generation_concurrency_defaults_are_cost_safe() -> None:
    settings = Settings(_env_file=None)

    assert settings.max_concurrent_generations_per_user == 1
    assert settings.generation_timeout_seconds == 120
    assert settings.context_rounds == 5
    assert settings.max_output_tokens <= 1024


def test_production_rejects_fail_open_configuration() -> None:
    try:
        Settings(_env_file=None, environment="production")
    except ValidationError as exc:
        assert "Unsafe production configuration" in str(exc)
    else:
        raise AssertionError("Production must reject unsafe defaults")


def test_production_accepts_complete_configuration() -> None:
    settings = Settings(
        _env_file=None,
        environment="production",
        app_secret="a" * 48,
        frontend_url="https://chat.rhythmusic.site",
        database_url="postgresql+asyncpg://user:unique@db/chat",
        cookie_secure=True,
        trusted_hosts=["chat.rhythmusic.site"],
        csrf_trusted_origins=["https://chat.rhythmusic.site"],
        turnstile_required=True,
        turnstile_secret_key="turnstile-secret",
        smtp_host="smtp.example.com",
        groq_api_key="provider-key",
        groq_model="provider/model",
    )
    assert settings.is_production
    assert settings.allowed_csrf_origins == {"https://chat.rhythmusic.site"}
