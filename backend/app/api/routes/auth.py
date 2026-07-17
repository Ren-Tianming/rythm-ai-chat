import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentAuth, get_current_auth, require_csrf
from app.core.config import Settings, get_settings
from app.core.security import (
    expires_in,
    hash_password,
    new_token,
    token_digest,
    utc_now,
    verify_password,
)
from app.db.models import (
    AuditLog,
    AuthSession,
    EmailVerificationToken,
    PasswordResetToken,
    User,
)
from app.db.session import get_db
from app.schemas.auth import (
    AuthResponse,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    ResetPasswordRequest,
    SessionResponse,
    UserResponse,
    VerifyEmailRequest,
)
from app.services.anti_abuse import verify_turnstile
from app.services.mail import send_reset_email, send_verification_email


router = APIRouter(prefix="/auth", tags=["auth"])


def normalized_email(email: str) -> str:
    return email.strip().casefold()


def user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        locale=user.locale,
        role=user.role,
        email_verified=user.email_verified_at is not None,
    )


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else None


def set_auth_cookies(response: Response, session_token: str, csrf_token: str, settings: Settings) -> None:
    max_age = settings.session_absolute_days * 86400
    response.set_cookie(
        settings.session_cookie_name,
        session_token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post("/register", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
async def register(
    payload: RegisterRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MessageResponse:
    await verify_turnstile(payload.turnstile_token, client_ip(request), settings)
    normalized = normalized_email(str(payload.email))
    existing = await db.scalar(select(User).where(User.normalized_email == normalized))
    if existing:
        return MessageResponse(message="If the address can be registered, a verification email was sent")
    user = User(
        email=str(payload.email),
        normalized_email=normalized,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name,
        locale=payload.locale,
    )
    db.add(user)
    await db.flush()
    raw_token = new_token()
    db.add(
        EmailVerificationToken(
            user_id=user.id,
            token_hash=token_digest(raw_token),
            expires_at=expires_in(hours=24),
        )
    )
    db.add(AuditLog(user_id=user.id, event_type="user_registered", ip_address=client_ip(request)))
    await db.commit()
    background_tasks.add_task(send_verification_email, user.email, raw_token, settings)
    return MessageResponse(message="If the address can be registered, a verification email was sent")


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(payload: VerifyEmailRequest, db: AsyncSession = Depends(get_db)) -> MessageResponse:
    token = await db.scalar(
        select(EmailVerificationToken).where(
            EmailVerificationToken.token_hash == token_digest(payload.token),
            EmailVerificationToken.used_at.is_(None),
            EmailVerificationToken.expires_at > utc_now(),
        )
    )
    if not token:
        raise HTTPException(status_code=400, detail="Verification link is invalid or expired")
    user = await db.get(User, token.user_id)
    if not user:
        raise HTTPException(status_code=400, detail="Verification link is invalid")
    token.used_at = utc_now()
    user.status = "active"
    user.email_verified_at = utc_now()
    db.add(AuditLog(user_id=user.id, event_type="email_verified"))
    await db.commit()
    return MessageResponse(message="Email verified")


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthResponse:
    await verify_turnstile(payload.turnstile_token, client_ip(request), settings)
    user = await db.scalar(
        select(User).where(User.normalized_email == normalized_email(str(payload.email)))
    )
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if user.status == "pending_verification":
        raise HTTPException(status_code=403, detail="Email is not verified")
    if user.status != "active":
        raise HTTPException(status_code=403, detail="Account is not active")
    session_token, csrf_token = new_token(), new_token(32)
    auth_session = AuthSession(
        user_id=user.id,
        token_hash=token_digest(session_token),
        csrf_hash=token_digest(csrf_token),
        user_agent=request.headers.get("user-agent", "")[:512],
        ip_address=client_ip(request),
        expires_at=expires_in(days=settings.session_absolute_days),
    )
    db.add(auth_session)
    user.last_login_at = utc_now()
    db.add(AuditLog(user_id=user.id, event_type="login_succeeded", ip_address=client_ip(request)))
    await db.commit()
    set_auth_cookies(response, session_token, csrf_token, settings)
    return AuthResponse(user=user_response(user), csrf_token=csrf_token)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    response: Response,
    auth: CurrentAuth = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MessageResponse:
    await db.delete(auth.session)
    await db.commit()
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")
    return MessageResponse(message="Logged out")


@router.get("/me", response_model=UserResponse)
async def me(auth: CurrentAuth = Depends(get_current_auth)) -> UserResponse:
    return user_response(auth.user)


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MessageResponse:
    await verify_turnstile(payload.turnstile_token, client_ip(request), settings)
    user = await db.scalar(
        select(User).where(User.normalized_email == normalized_email(str(payload.email)))
    )
    if user and user.status == "active":
        raw_token = new_token()
        db.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=token_digest(raw_token),
                expires_at=expires_in(minutes=30),
            )
        )
        await db.commit()
        background_tasks.add_task(send_reset_email, user.email, raw_token, settings)
    return MessageResponse(message="If the account exists, a reset email was sent")


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    token = await db.scalar(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_digest(payload.token),
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > utc_now(),
        )
    )
    if not token:
        raise HTTPException(status_code=400, detail="Reset link is invalid or expired")
    user = await db.get(User, token.user_id)
    if not user:
        raise HTTPException(status_code=400, detail="Reset link is invalid")
    user.password_hash = hash_password(payload.password)
    token.used_at = utc_now()
    await db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    db.add(AuditLog(user_id=user.id, event_type="password_reset"))
    await db.commit()
    return MessageResponse(message="Password reset completed")


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    payload: ChangePasswordRequest,
    auth: CurrentAuth = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    if not verify_password(payload.current_password, auth.user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    auth.user.password_hash = hash_password(payload.new_password)
    await db.execute(
        delete(AuthSession).where(
            AuthSession.user_id == auth.user.id,
            AuthSession.id != auth.session.id,
        )
    )
    db.add(AuditLog(user_id=auth.user.id, event_type="password_changed"))
    await db.commit()
    return MessageResponse(message="Password changed")


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(
    auth: CurrentAuth = Depends(get_current_auth), db: AsyncSession = Depends(get_db)
) -> list[SessionResponse]:
    sessions = (
        await db.scalars(
            select(AuthSession)
            .where(AuthSession.user_id == auth.user.id, AuthSession.expires_at > utc_now())
            .order_by(AuthSession.last_seen_at.desc())
        )
    ).all()
    return [
        SessionResponse(
            id=item.id,
            user_agent=item.user_agent,
            ip_address=item.ip_address,
            last_seen_at=item.last_seen_at,
            created_at=item.created_at,
            current=item.id == auth.session.id,
        )
        for item in sessions
    ]


@router.delete("/sessions/{session_id}", response_model=MessageResponse)
async def revoke_session(
    session_id: uuid.UUID,
    auth: CurrentAuth = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    session = await db.scalar(
        select(AuthSession).where(
            AuthSession.id == session_id,
            AuthSession.user_id == auth.user.id,
        )
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    await db.delete(session)
    await db.commit()
    return MessageResponse(message="Session revoked")
