import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.security import utc_now
from app.db.base import Base


def uuid_pk() -> uuid.UUID:
    return uuid.uuid4()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("status IN ('pending_verification','active','suspended','deleted')"),
        CheckConstraint("role IN ('user','admin')"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid_pk)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    normalized_email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(50))
    locale: Mapped[str] = mapped_column(String(10), default="zh-CN", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending_verification", nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="user", nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    sessions: Mapped[list["AuthSession"]] = relationship(cascade="all, delete-orphan")
    conversations: Mapped[list["Conversation"]] = relationship(cascade="all, delete-orphan")


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (Index("ix_auth_sessions_user_expires", "user_id", "expires_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid_pk)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    csrf_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(512))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OneTimeTokenMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid_pk)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EmailVerificationToken(Base, OneTimeTokenMixin):
    __tablename__ = "email_verification_tokens"


class PasswordResetToken(Base, OneTimeTokenMixin):
    __tablename__ = "password_reset_tokens"


class ModelProfile(Base, TimestampMixin):
    __tablename__ = "model_profiles"
    __table_args__ = (CheckConstraint("provider IN ('deepseek','gemini','groq')"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid_pk)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    model_id: Mapped[str] = mapped_column(String(160), nullable=False)
    description_key: Mapped[str] = mapped_column(String(120), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    max_output_tokens: Mapped[int] = mapped_column(Integer, default=8192, nullable=False)
    display_name_i18n: Mapped[dict[str, str]] = mapped_column(JSON, default=dict, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    context_rounds: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    default_output_tokens: Mapped[int] = mapped_column(Integer, default=8192, nullable=False)
    input_price_per_million: Mapped[float | None] = mapped_column(Numeric(12, 6))
    output_price_per_million: Mapped[float | None] = mapped_column(Numeric(12, 6))
    pricing_version: Mapped[str | None] = mapped_column(String(40))
    config_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)


class Conversation(Base, TimestampMixin):
    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_user_updated", "user_id", "updated_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid_pk)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    model_profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("model_profiles.id"))
    title: Mapped[str] = mapped_column(String(100), default="New conversation", nullable=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    messages: Mapped[list["Message"]] = relationship(cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "sequence_no"),
        CheckConstraint("role IN ('user','assistant')"),
        CheckConstraint("status IN ('completed','failed','cancelled','streaming')"),
        Index("ix_messages_conversation_sequence", "conversation_id", "sequence_no"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid_pk)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="completed", nullable=False)
    model_profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("model_profiles.id"))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    finish_reason: Mapped[str | None] = mapped_column(String(80))
    continuation_of_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Generation(Base):
    __tablename__ = "generations"
    __table_args__ = (
        CheckConstraint("status IN ('pending','streaming','completed','failed','cancelled')"),
        UniqueConstraint("user_id", "client_request_id"),
        Index("ix_generations_conversation_created", "conversation_id", "created_at"),
        Index("ix_generations_conversation_status", "conversation_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid_pk)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    client_request_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    user_message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("messages.id"), unique=True)
    assistant_message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("messages.id"))
    model_profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("model_profiles.id"))
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    provider_request_id: Mapped[str | None] = mapped_column(String(200))
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_detail_redacted: Mapped[str | None] = mapped_column(String(500))
    context_truncated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latency_ms: Mapped[int | None] = mapped_column(Integer)


class UsageEvent(Base):
    __tablename__ = "usage_events"
    __table_args__ = (Index("ix_usage_events_user_created", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid_pk)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    generation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("generations.id"), unique=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model_id: Mapped[str] = mapped_column(String(160), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost_microusd: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    pricing_version: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_user_created", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid_pk)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(80))
    target_id: Mapped[str | None] = mapped_column(String(100))
    result: Mapped[str] = mapped_column(String(32), default="success", nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    request_id: Mapped[str | None] = mapped_column(String(80))
    details: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class UserConsent(Base):
    __tablename__ = "user_consents"
    __table_args__ = (
        UniqueConstraint("user_id", "document_type", "document_version"),
        Index("ix_user_consents_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid_pk)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    document_type: Mapped[str] = mapped_column(String(40), nullable=False)
    document_version: Mapped[str] = mapped_column(String(40), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Document(Base, TimestampMixin):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("status IN ('pending','processing','ready','failed')"),
        Index("ix_documents_owner_conversation", "user_id", "conversation_id"),
        Index("ix_documents_queue", "status", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid_pk)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(80), unique=True)
    mime_type: Mapped[str] = mapped_column(String(80))
    size_bytes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(300))
    page_count: Mapped[int | None] = mapped_column(Integer)
    embedding_model: Mapped[str | None] = mapped_column(String(160))
    embedding_version: Mapped[str | None] = mapped_column(String(160))
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer)
    processing_token: Mapped[uuid.UUID | None] = mapped_column()
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (Index("ix_document_chunks_document", "document_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid_pk)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    ordinal: Mapped[int] = mapped_column(Integer)
    page_number: Mapped[int | None] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer)
    # Unbounded Vector allows coexistence of model versions/dimensions. Filter before distance.
    embedding: Mapped[list[float]] = mapped_column(Vector().with_variant(JSON(), "sqlite"))
    embedding_model: Mapped[str] = mapped_column(String(160))
    embedding_version: Mapped[str] = mapped_column(String(160))
    embedding_dimensions: Mapped[int] = mapped_column(Integer)


class MessageSource(Base):
    __tablename__ = "message_sources"
    __table_args__ = (Index("ix_message_sources_message", "message_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid_pk)
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"))
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="CASCADE")
    )
    source_kind: Mapped[str] = mapped_column(String(16), default="retrieval")
    label: Mapped[str] = mapped_column(String(16))
    excerpt: Mapped[str] = mapped_column(Text)
    similarity: Mapped[float] = mapped_column(Numeric(8, 6))


class DocumentUsage(Base):
    __tablename__ = "document_usage"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid_pk)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    model: Mapped[str] = mapped_column(String(160))
    purpose: Mapped[str] = mapped_column(String(16))
    input_tokens: Mapped[int] = mapped_column(Integer)
    estimated_cost_microusd: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
