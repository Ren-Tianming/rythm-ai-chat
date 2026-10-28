import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ModelProfileResponse(BaseModel):
    id: uuid.UUID
    slug: str
    provider: str
    display_name: str
    description_key: str
    is_default: bool
    max_output_tokens: int
    supports_vision: bool = False


class ConversationCreate(BaseModel):
    model_profile_id: uuid.UUID


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    model_profile_id: uuid.UUID | None = None
    archived: bool | None = None


class ConversationResponse(BaseModel):
    id: uuid.UUID
    title: str
    model_profile_id: uuid.UUID
    archived: bool
    created_at: datetime
    updated_at: datetime


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    model_profile_id: uuid.UUID | None = None
    client_request_id: uuid.UUID
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    continue_message_id: uuid.UUID | None = None


class ChatMessageResponse(BaseModel):
    id: uuid.UUID
    sequence_no: int
    role: str
    content: str
    status: str
    model_profile_id: uuid.UUID | None
    input_tokens: int | None
    output_tokens: int | None
    created_at: datetime
    finish_reason: str | None = None
    sources: list[dict] = Field(default_factory=list)


class UsageSummaryResponse(BaseModel):
    requests_today: int
    daily_limit: int
    input_tokens: int
    output_tokens: int
    estimated_cost_microusd: int
