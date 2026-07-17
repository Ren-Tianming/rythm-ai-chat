import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


SUPPORTED_LOCALES = {"zh", "ja", "en"}


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    display_name: str | None = Field(default=None, max_length=80)
    locale: str = "zh"
    turnstile_token: str | None = None

    @field_validator("locale")
    @classmethod
    def valid_locale(cls, value: str) -> str:
        if value not in SUPPORTED_LOCALES:
            raise ValueError("Unsupported locale")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    turnstile_token: str | None = None


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=20, max_length=300)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr
    turnstile_token: str | None = None


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=20, max_length=300)
    password: str = Field(min_length=12, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    display_name: str | None
    locale: str
    role: str
    email_verified: bool


class AuthResponse(BaseModel):
    user: UserResponse
    csrf_token: str


class SessionResponse(BaseModel):
    id: uuid.UUID
    user_agent: str | None
    ip_address: str | None
    last_seen_at: datetime
    created_at: datetime
    current: bool = False


class MessageResponse(BaseModel):
    message: str
