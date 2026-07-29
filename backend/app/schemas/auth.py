import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.core.security import validate_display_name, validate_password_strength


SUPPORTED_LOCALES = {"zh-CN", "ja-JP", "en-US"}


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    password_confirm: str = Field(min_length=12, max_length=128)
    display_name: str | None = Field(default=None, max_length=50)
    locale: str = "zh-CN"
    terms_version: str = Field(min_length=1, max_length=40)
    terms_accepted: bool
    turnstile_token: str | None = None

    @field_validator("locale")
    @classmethod
    def valid_locale(cls, value: str) -> str:
        if value not in SUPPORTED_LOCALES:
            raise ValueError("Unsupported locale")
        return value

    @field_validator("password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        return validate_password_strength(value)

    @field_validator("display_name")
    @classmethod
    def valid_display_name(cls, value: str | None) -> str | None:
        return validate_display_name(value) if value is not None else None

    @model_validator(mode="after")
    def passwords_match(self) -> "RegisterRequest":
        if self.password != self.password_confirm:
            raise ValueError("Passwords do not match")
        if not self.terms_accepted:
            raise ValueError("Terms must be accepted")
        return self


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
    password_confirm: str = Field(min_length=12, max_length=128)

    @field_validator("password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        return validate_password_strength(value)

    @model_validator(mode="after")
    def passwords_match(self) -> "ResetPasswordRequest":
        if self.password != self.password_confirm:
            raise ValueError("Passwords do not match")
        return self


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)
    new_password_confirm: str = Field(min_length=12, max_length=128)

    @field_validator("new_password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        return validate_password_strength(value)

    @model_validator(mode="after")
    def passwords_match(self) -> "ChangePasswordRequest":
        if self.new_password != self.new_password_confirm:
            raise ValueError("Passwords do not match")
        return self


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
