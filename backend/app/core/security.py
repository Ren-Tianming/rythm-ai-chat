import hashlib
import secrets
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


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def expires_in(*, minutes: int = 0, hours: int = 0, days: int = 0) -> datetime:
    return utc_now() + timedelta(minutes=minutes, hours=hours, days=days)
