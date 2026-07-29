import pytest
from pydantic import ValidationError

from app.schemas.auth import RegisterRequest


def valid_registration() -> dict:
    return {
        "email": "person@example.com",
        "password": "correct horse battery staple",
        "password_confirm": "correct horse battery staple",
        "locale": "ja-JP",
        "terms_version": "2026-07-29",
        "terms_accepted": True,
    }


def test_registration_requires_matching_passwords_and_consent() -> None:
    assert RegisterRequest(**valid_registration()).locale == "ja-JP"

    mismatch = valid_registration()
    mismatch["password_confirm"] = "different password value"
    with pytest.raises(ValidationError):
        RegisterRequest(**mismatch)

    no_consent = valid_registration()
    no_consent["terms_accepted"] = False
    with pytest.raises(ValidationError):
        RegisterRequest(**no_consent)
