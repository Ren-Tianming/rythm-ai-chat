import httpx
from fastapi import HTTPException, status

from app.core.config import Settings


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
