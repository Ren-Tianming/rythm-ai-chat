"""Initial RyThM Chatbot schema.

Revision ID: 0001_initial
Revises:
"""

import uuid

import sqlalchemy as sa
from alembic import op


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("normalized_email", sa.String(320), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("display_name", sa.String(80)),
        sa.Column("locale", sa.String(8), server_default="zh", nullable=False),
        sa.Column("status", sa.String(32), server_default="pending_verification", nullable=False),
        sa.Column("role", sa.String(16), server_default="user", nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True)),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.CheckConstraint("status IN ('pending_verification','active','suspended','deleted')"),
        sa.CheckConstraint("role IN ('user','admin')"),
    )
    op.create_table(
        "model_profiles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("slug", sa.String(80), nullable=False, unique=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("model_id", sa.String(160), nullable=False),
        sa.Column("description_key", sa.String(120), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("max_output_tokens", sa.Integer(), server_default="512", nullable=False),
        *timestamps(),
        sa.CheckConstraint("provider IN ('deepseek','gemini','groq')"),
    )
    op.bulk_insert(
        sa.table(
            "model_profiles",
            sa.column("id", sa.Uuid()),
            sa.column("slug", sa.String()),
            sa.column("provider", sa.String()),
            sa.column("display_name", sa.String()),
            sa.column("model_id", sa.String()),
            sa.column("description_key", sa.String()),
            sa.column("enabled", sa.Boolean()),
            sa.column("is_default", sa.Boolean()),
            sa.column("max_output_tokens", sa.Integer()),
        ),
        [
            {
                "id": uuid.UUID("10000000-0000-4000-8000-000000000001"),
                "slug": "deepseek-v4-flash",
                "provider": "deepseek",
                "display_name": "DeepSeek V4 Flash",
                "model_id": "deepseek-v4-flash",
                "description_key": "models.deepseek",
                "enabled": True,
                "is_default": True,
                "max_output_tokens": 512,
            },
            {
                "id": uuid.UUID("10000000-0000-4000-8000-000000000002"),
                "slug": "gemini-3-1-flash-lite",
                "provider": "gemini",
                "display_name": "Gemini 3.1 Flash-Lite",
                "model_id": "gemini-3.1-flash-lite",
                "description_key": "models.gemini",
                "enabled": True,
                "is_default": False,
                "max_output_tokens": 512,
            },
            {
                "id": uuid.UUID("10000000-0000-4000-8000-000000000003"),
                "slug": "groq-gpt-oss-20b",
                "provider": "groq",
                "display_name": "Groq GPT-OSS 20B",
                "model_id": "openai/gpt-oss-20b",
                "description_key": "models.groq",
                "enabled": True,
                "is_default": False,
                "max_output_tokens": 512,
            },
        ],
    )
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("csrf_hash", sa.String(64), nullable=False),
        sa.Column("user_agent", sa.String(512)),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_auth_sessions_user_expires", "auth_sessions", ["user_id", "expires_at"])
    for table_name in ("email_verification_tokens", "password_reset_tokens"):
        op.create_table(
            table_name,
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model_profile_id", sa.Uuid(), sa.ForeignKey("model_profiles.id"), nullable=False),
        sa.Column("title", sa.String(160), server_default="New conversation", nullable=False),
        sa.Column("archived", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        *timestamps(),
    )
    op.create_index("ix_conversations_user_updated", "conversations", ["user_id", "updated_at"])
    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("conversation_id", sa.Uuid(), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), server_default="completed", nullable=False),
        sa.Column("model_profile_id", sa.Uuid(), sa.ForeignKey("model_profiles.id")),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("finish_reason", sa.String(80)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("conversation_id", "sequence_no"),
        sa.CheckConstraint("role IN ('user','assistant')"),
        sa.CheckConstraint("status IN ('completed','failed','cancelled','streaming')"),
    )
    op.create_index("ix_messages_conversation_sequence", "messages", ["conversation_id", "sequence_no"])
    op.create_table(
        "generations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("conversation_id", sa.Uuid(), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_message_id", sa.Uuid(), sa.ForeignKey("messages.id"), nullable=False),
        sa.Column("assistant_message_id", sa.Uuid(), sa.ForeignKey("messages.id")),
        sa.Column("model_profile_id", sa.Uuid(), sa.ForeignKey("model_profiles.id"), nullable=False),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("provider_request_id", sa.String(200)),
        sa.Column("error_code", sa.String(80)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('pending','streaming','completed','failed','cancelled')"),
    )
    op.create_table(
        "usage_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("generation_id", sa.Uuid(), sa.ForeignKey("generations.id"), nullable=False, unique=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model_id", sa.String(160), nullable=False),
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("estimated_cost_microusd", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_usage_events_user_created", "usage_events", ["user_id", "created_at"])
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("user_agent", sa.String(512)),
        sa.Column("details", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_logs_user_created", "audit_logs", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("usage_events")
    op.drop_table("generations")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("password_reset_tokens")
    op.drop_table("email_verification_tokens")
    op.drop_table("auth_sessions")
    op.drop_table("model_profiles")
    op.drop_table("users")
