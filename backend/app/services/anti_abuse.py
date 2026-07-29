import asyncio
import time
from collections import defaultdict, deque

import httpx
from fastapi import HTTPException, status

from app.core.config import Settings


class InMemoryRateLimiter:
    """Single-worker limiter for the MVP deployment profile."""

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def check(self, key: str, limit: int, window_seconds: int) -> None:
        now = time.monotonic()
        cutoff = now - window_seconds
        async with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                retry_after = max(1, int(events[0] + window_seconds - now))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "code": "RATE_LIMITED",
                        "message": "Too many requests. Please try again later.",
                        "details": {"retry_after": retry_after},
                    },
                    headers={"Retry-After": str(retry_after)},
                )
            events.append(now)


rate_limiter = InMemoryRateLimiter()


async def verify_turnstile(
    token: str | None, remote_ip: str | None, settings: Settings
) -> None:
    if not settings.turnstile_secret_key:
        if settings.turnstile_required:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Human verification is not configured",
            )
        return
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Human verification is required",
        )
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data={
                "secret": settings.turnstile_secret_key,
                "response": token,
                "remoteip": remote_ip or "",
            },
        )
    if not response.is_success or not response.json().get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Human verification failed",
        )
