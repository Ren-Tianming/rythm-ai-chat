from pydantic import BaseModel, Field, field_validator

from app.core.security import validate_display_name
from app.schemas.auth import SUPPORTED_LOCALES


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=50)
    locale: str | None = None

    @field_validator("locale")
    @classmethod
    def valid_locale(cls, value: str | None) -> str | None:
        if value is not None and value not in SUPPORTED_LOCALES:
            raise ValueError("Unsupported locale")
        return value

    @field_validator("display_name")
    @classmethod
    def valid_display_name(cls, value: str | None) -> str | None:
        return validate_display_name(value) if value is not None else None
