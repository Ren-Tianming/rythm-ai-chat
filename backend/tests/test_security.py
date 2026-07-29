from app.core.security import (
    hash_password,
    new_token,
    token_digest,
    validate_display_name,
    validate_password_strength,
    verify_password,
)


def test_password_round_trip() -> None:
    encoded = hash_password("correct horse battery staple")
    assert encoded != "correct horse battery staple"
    assert verify_password("correct horse battery staple", encoded)
    assert not verify_password("wrong password", encoded)


def test_tokens_are_random_and_hashed() -> None:
    first, second = new_token(), new_token()
    assert first != second
    assert len(token_digest(first)) == 64
    assert first not in token_digest(first)
    assert token_digest(first, "secret-a") != token_digest(first, "secret-b")


def test_password_and_display_name_rules() -> None:
    assert validate_password_strength("correct horse battery staple")
    assert validate_display_name("  Tianming  ") == "Tianming"
    for invalid in ("password1234", "hello\u0000world123"):
        try:
            validate_password_strength(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError("Weak or control-character passwords must be rejected")
