from app.core.config import Settings
from app.services.mail import build_account_action_url


def test_account_action_url_keeps_token_out_of_http_request() -> None:
    settings = Settings(_env_file=None, frontend_url="https://chat.example.com/")

    url = build_account_action_url("reset", "secret/token?value", settings)

    assert url == "https://chat.example.com/#reset=secret%2Ftoken%3Fvalue"
    assert "?reset=" not in url


def test_account_action_url_rejects_unknown_action() -> None:
    settings = Settings(_env_file=None, frontend_url="https://chat.example.com")

    try:
        build_account_action_url("unknown", "token", settings)
    except ValueError as exc:
        assert str(exc) == "Unsupported account action"
    else:
        raise AssertionError("Unknown account actions must be rejected")
