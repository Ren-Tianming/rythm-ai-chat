import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy import select, update
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
    UserConsent,
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
from app.services.anti_abuse import rate_limiter, verify_turnstile
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


def default_display_name(email: str) -> str:
    candidate = "".join(char for char in email.split("@", 1)[0].strip() if char.isprintable())
    return (candidate or "User")[:50]


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
    remote_ip = client_ip(request) or "unknown"
    await rate_limiter.check(f"register:ip:{remote_ip}", 5, 3600)
    await verify_turnstile(payload.turnstile_token, client_ip(request), settings)
    if payload.terms_version != settings.terms_version:
        raise HTTPException(
            status_code=422,
            detail={"code": "CONSENT_REQUIRED", "message": "The terms version is not current"},
        )
    normalized = normalized_email(str(payload.email))
    existing = await db.scalar(select(User).where(User.normalized_email == normalized))
    if existing:
        return MessageResponse(message="If the address can be registered, a verification email was sent")
    user = User(
        email=str(payload.email),
        normalized_email=normalized,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name or default_display_name(normalized),
        locale=payload.locale,
    )
    db.add(user)
    await db.flush()
    raw_token = new_token()
    db.add(
        EmailVerificationToken(
            user_id=user.id,
            token_hash=token_digest(raw_token, settings.app_secret),
            expires_at=expires_in(hours=24),
        )
    )
    db.add(
        UserConsent(
            user_id=user.id,
            document_type="terms",
            document_version=payload.terms_version,
            ip_address=client_ip(request),
        )
    )
    db.add(
        AuditLog(
            user_id=user.id,
            event_type="user_registered",
            ip_address=client_ip(request),
            user_agent=request.headers.get("user-agent", "")[:512],
            request_id=getattr(request.state, "request_id", None),
        )
    )
    await db.commit()
    background_tasks.add_task(send_verification_email, user.email, raw_token, settings)
    return MessageResponse(message="If the address can be registered, a verification email was sent")


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(
    payload: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MessageResponse:
    token = await db.scalar(
        select(EmailVerificationToken).where(
            EmailVerificationToken.token_hash == token_digest(payload.token, settings.app_secret),
            EmailVerificationToken.used_at.is_(None),
            EmailVerificationToken.expires_at > utc_now(),
        ).with_for_update()
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


@router.post("/resend-verification", response_model=MessageResponse)
async def resend_verification(
    payload: ForgotPasswordRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MessageResponse:
    normalized = normalized_email(str(payload.email))
    remote_ip = client_ip(request) or "unknown"
    await rate_limiter.check(f"resend:email:{normalized}", 3, 3600)
    await rate_limiter.check(f"resend:ip:{remote_ip}", 10, 3600)
    await verify_turnstile(payload.turnstile_token, client_ip(request), settings)
    user = await db.scalar(select(User).where(User.normalized_email == normalized))
    if user and user.status == "pending_verification":
        now = utc_now()
        await db.execute(
            update(EmailVerificationToken)
            .where(
                EmailVerificationToken.user_id == user.id,
                EmailVerificationToken.used_at.is_(None),
            )
            .values(used_at=now)
        )
        raw_token = new_token()
        db.add(
            EmailVerificationToken(
                user_id=user.id,
                token_hash=token_digest(raw_token, settings.app_secret),
                expires_at=expires_in(hours=24),
            )
        )
        await db.commit()
        background_tasks.add_task(send_verification_email, user.email, raw_token, settings)
    return MessageResponse(message="If the account can be verified, an email was sent")


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthResponse:
    normalized = normalized_email(str(payload.email))
    remote_ip = client_ip(request) or "unknown"
    await rate_limiter.check(f"login:{normalized}:{remote_ip}", 5, 600)
    await verify_turnstile(payload.turnstile_token, client_ip(request), settings)
    user = await db.scalar(select(User).where(User.normalized_email == normalized))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if user.status == "pending_verification":
        raise HTTPException(status_code=403, detail="Email is not verified")
    if user.status != "active":
        raise HTTPException(status_code=403, detail="Account is not active")
    session_token, csrf_token = new_token(), new_token(32)
    absolute_expires_at = expires_in(days=settings.session_absolute_days)
    idle_expires_at = expires_in(hours=settings.session_idle_hours)
    auth_session = AuthSession(
        user_id=user.id,
        token_hash=token_digest(session_token, settings.app_secret),
        csrf_hash=token_digest(csrf_token, settings.app_secret),
        user_agent=request.headers.get("user-agent", "")[:512],
        ip_address=client_ip(request),
        expires_at=absolute_expires_at,
        idle_expires_at=idle_expires_at,
        absolute_expires_at=absolute_expires_at,
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
    auth.session.revoked_at = utc_now()
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
    normalized = normalized_email(str(payload.email))
    remote_ip = client_ip(request) or "unknown"
    await rate_limiter.check(f"forgot:email:{normalized}", 3, 3600)
    await rate_limiter.check(f"forgot:ip:{remote_ip}", 10, 3600)
    await verify_turnstile(payload.turnstile_token, client_ip(request), settings)
    user = await db.scalar(select(User).where(User.normalized_email == normalized))
    if user and user.status == "active":
        now = utc_now()
        await db.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.used_at.is_(None),
            )
            .values(used_at=now)
        )
        raw_token = new_token()
        db.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=token_digest(raw_token, settings.app_secret),
                expires_at=expires_in(minutes=30),
            )
        )
        await db.commit()
        background_tasks.add_task(send_reset_email, user.email, raw_token, settings)
    return MessageResponse(message="If the account exists, a reset email was sent")


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MessageResponse:
    token = await db.scalar(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_digest(payload.token, settings.app_secret),
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > utc_now(),
        ).with_for_update()
    )
    if not token:
        raise HTTPException(status_code=400, detail="Reset link is invalid or expired")
    user = await db.get(User, token.user_id)
    if not user:
        raise HTTPException(status_code=400, detail="Reset link is invalid")
    if verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=422, detail="New password must be different")
    now = utc_now()
    user.password_hash = hash_password(payload.password)
    await db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    await db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    db.add(AuditLog(user_id=user.id, event_type="password_reset"))
    await db.commit()
    return MessageResponse(message="Password reset completed")


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    auth: CurrentAuth = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MessageResponse:
    if not verify_password(payload.current_password, auth.user.password_hash):
        db.add(
            AuditLog(
                user_id=auth.user.id,
                event_type="password_change_failed",
                result="failure",
                request_id=getattr(request.state, "request_id", None),
            )
        )
        await db.commit()
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if verify_password(payload.new_password, auth.user.password_hash):
        raise HTTPException(status_code=422, detail="New password must be different")
    now = utc_now()
    auth.user.password_hash = hash_password(payload.new_password)
    await db.execute(
        update(AuthSession)
        .where(
            AuthSession.user_id == auth.user.id,
            AuthSession.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    session_token, csrf_token = new_token(), new_token(32)
    absolute_expires_at = expires_in(days=settings.session_absolute_days)
    db.add(
        AuthSession(
            user_id=auth.user.id,
            token_hash=token_digest(session_token, settings.app_secret),
            csrf_hash=token_digest(csrf_token, settings.app_secret),
            user_agent=request.headers.get("user-agent", "")[:512],
            ip_address=client_ip(request),
            expires_at=absolute_expires_at,
            idle_expires_at=expires_in(hours=settings.session_idle_hours),
            absolute_expires_at=absolute_expires_at,
        )
    )
    db.add(
        AuditLog(
            user_id=auth.user.id,
            event_type="password_changed",
            request_id=getattr(request.state, "request_id", None),
        )
    )
    await db.commit()
    set_auth_cookies(response, session_token, csrf_token, settings)
    return MessageResponse(message="Password changed")


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(
    auth: CurrentAuth = Depends(get_current_auth), db: AsyncSession = Depends(get_db)
) -> list[SessionResponse]:
    sessions = (
        await db.scalars(
            select(AuthSession)
            .where(
                AuthSession.user_id == auth.user.id,
                AuthSession.absolute_expires_at > utc_now(),
                AuthSession.idle_expires_at > utc_now(),
                AuthSession.revoked_at.is_(None),
            )
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
    session.revoked_at = utc_now()
    await db.commit()
    return MessageResponse(message="Session revoked")
