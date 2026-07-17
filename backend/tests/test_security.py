from app.core.security import hash_password, new_token, token_digest, verify_password


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
