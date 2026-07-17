import uuid
from dataclasses import dataclass
from datetime import timedelta

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import token_digest, utc_now
from app.db.models import AuthSession, User
from app.db.session import get_db


@dataclass
class CurrentAuth:
    user: User
    session: AuthSession


async def get_current_auth(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CurrentAuth:
    raw_token = request.cookies.get(settings.session_cookie_name)
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    result = await db.execute(
        select(AuthSession, User)
        .join(User, User.id == AuthSession.user_id)
        .where(AuthSession.token_hash == token_digest(raw_token))
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    auth_session, user = row
    now = utc_now()
    idle_deadline = now - timedelta(hours=settings.session_idle_hours)
    if (
        auth_session.expires_at <= now
        or auth_session.last_seen_at <= idle_deadline
        or user.status != "active"
    ):
        await db.delete(auth_session)
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    auth_session.last_seen_at = now
    await db.commit()
    return CurrentAuth(user=user, session=auth_session)


async def require_csrf(
    request: Request,
    auth: CurrentAuth = Depends(get_current_auth),
    settings: Settings = Depends(get_settings),
    csrf_header: str | None = Header(default=None, alias="X-CSRF-Token"),
    csrf_cookie: str | None = Cookie(default=None, alias="rythm_csrf"),
) -> CurrentAuth:
    cookie_value = request.cookies.get(settings.csrf_cookie_name) or csrf_cookie
    if (
        not csrf_header
        or not cookie_value
        or not secrets_equal(csrf_header, cookie_value)
        or token_digest(csrf_header) != auth.session.csrf_hash
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")
    return auth


def secrets_equal(left: str, right: str) -> bool:
    import hmac

    return hmac.compare_digest(left.encode(), right.encode())


async def owned_conversation(
    conversation_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    db: AsyncSession = Depends(get_db),
):
    from app.db.models import Conversation

    conversation = await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == auth.user.id,
            Conversation.deleted_at.is_(None),
        )
    )
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conversation
