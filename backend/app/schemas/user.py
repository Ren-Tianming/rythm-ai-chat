from pydantic import BaseModel, Field, field_validator

from app.schemas.auth import SUPPORTED_LOCALES


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=80)
    locale: str | None = None

    @field_validator("locale")
    @classmethod
    def valid_locale(cls, value: str | None) -> str | None:
        if value is not None and value not in SUPPORTED_LOCALES:
            raise ValueError("Unsupported locale")
        return value
