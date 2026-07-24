from app.core.config import Settings


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
