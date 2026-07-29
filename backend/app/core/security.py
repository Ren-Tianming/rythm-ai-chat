import hashlib
import hmac
import secrets
import unicodedata
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError


password_hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)


def utc_now() -> datetime:
    return datetime.now(UTC)


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return password_hasher.verify(encoded, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def new_token(length: int = 48) -> str:
    return secrets.token_urlsafe(length)


def token_digest(token: str, secret: str = "") -> str:
    if secret:
        return hmac.new(secret.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


COMMON_PASSWORDS = {
    "123456789012",
    "password1234",
    "qwerty123456",
    "letmein123456",
    "admin12345678",
}


def validate_password_strength(password: str) -> str:
    if password.casefold() in COMMON_PASSWORDS:
        raise ValueError("Password is too common")
    if any(unicodedata.category(char).startswith("C") for char in password):
        raise ValueError("Password contains unsupported control characters")
    return password


def validate_display_name(value: str) -> str:
    normalized = value.strip()
    if not 1 <= len(normalized) <= 50:
        raise ValueError("Display name must contain 1 to 50 characters")
    if any(unicodedata.category(char).startswith("C") for char in normalized):
        raise ValueError("Display name contains unsupported control characters")
    return normalized


def expires_in(*, minutes: int = 0, hours: int = 0, days: int = 0) -> datetime:
    return utc_now() + timedelta(minutes=minutes, hours=hours, days=days)
