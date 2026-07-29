"""Complete the production baseline schema.

Revision ID: 0003_production_baseline
Revises: 0002_generation_quota_indexes
"""

import sqlalchemy as sa
from alembic import op


revision = "0003_production_baseline"
down_revision = "0002_generation_quota_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("users", "display_name", type_=sa.String(50), existing_type=sa.String(80))
    op.execute(
        """
        UPDATE users SET locale = CASE locale
          WHEN 'zh' THEN 'zh-CN'
          WHEN 'ja' THEN 'ja-JP'
          WHEN 'en' THEN 'en-US'
          ELSE locale
        END
        """
    )
    op.alter_column("users", "locale", type_=sa.String(10), existing_type=sa.String(8))

    op.add_column("auth_sessions", sa.Column("idle_expires_at", sa.DateTime(timezone=True)))
    op.add_column("auth_sessions", sa.Column("absolute_expires_at", sa.DateTime(timezone=True)))
    op.add_column("auth_sessions", sa.Column("revoked_at", sa.DateTime(timezone=True)))
    op.execute(
        "UPDATE auth_sessions SET idle_expires_at = expires_at, absolute_expires_at = expires_at"
    )
    op.alter_column("auth_sessions", "idle_expires_at", nullable=False)
    op.alter_column("auth_sessions", "absolute_expires_at", nullable=False)

    op.add_column(
        "model_profiles",
        sa.Column("display_name_i18n", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
    )
    op.add_column(
        "model_profiles", sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column(
        "model_profiles", sa.Column("context_rounds", sa.Integer(), server_default="5", nullable=False)
    )
    op.add_column(
        "model_profiles",
        sa.Column("default_output_tokens", sa.Integer(), server_default="512", nullable=False),
    )
    op.add_column("model_profiles", sa.Column("input_price_per_million", sa.Numeric(12, 6)))
    op.add_column("model_profiles", sa.Column("output_price_per_million", sa.Numeric(12, 6)))
    op.add_column("model_profiles", sa.Column("pricing_version", sa.String(40)))
    op.add_column(
        "model_profiles",
        sa.Column("config_json", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
    )
    op.execute(
        """
        UPDATE model_profiles SET sort_order = CASE provider
          WHEN 'deepseek' THEN 10 WHEN 'gemini' THEN 20 ELSE 30 END
        """
    )
    op.alter_column("conversations", "title", type_=sa.String(100), existing_type=sa.String(160))

    op.add_column("generations", sa.Column("user_id", sa.Uuid()))
    op.add_column("generations", sa.Column("client_request_id", sa.Uuid()))
    op.add_column("generations", sa.Column("error_detail_redacted", sa.String(500)))
    op.add_column(
        "generations",
        sa.Column("context_truncated", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("generations", sa.Column("started_at", sa.DateTime(timezone=True)))
    op.add_column("generations", sa.Column("cancelled_at", sa.DateTime(timezone=True)))
    op.add_column("generations", sa.Column("latency_ms", sa.Integer()))
    op.execute(
        """
        UPDATE generations
        SET user_id = conversations.user_id
        FROM conversations
        WHERE generations.conversation_id = conversations.id
        """
    )
    op.alter_column("generations", "user_id", nullable=False)
    op.create_foreign_key(
        "fk_generations_user_id_users", "generations", "users", ["user_id"], ["id"], ondelete="CASCADE"
    )
    op.create_unique_constraint(
        "uq_generations_user_client_request", "generations", ["user_id", "client_request_id"]
    )
    op.create_unique_constraint(
        "uq_generations_user_message_id", "generations", ["user_message_id"]
    )

    op.add_column(
        "usage_events", sa.Column("total_tokens", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column("usage_events", sa.Column("pricing_version", sa.String(40)))
    op.execute("UPDATE usage_events SET total_tokens = input_tokens + output_tokens")

    op.add_column("audit_logs", sa.Column("target_type", sa.String(80)))
    op.add_column("audit_logs", sa.Column("target_id", sa.String(100)))
    op.add_column(
        "audit_logs", sa.Column("result", sa.String(32), server_default="success", nullable=False)
    )
    op.add_column("audit_logs", sa.Column("request_id", sa.String(80)))

    op.create_table(
        "user_consents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("document_type", sa.String(40), nullable=False),
        sa.Column("document_version", sa.String(40), nullable=False),
        sa.Column("ip_address", sa.String(64)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "user_id", "document_type", "document_version", name="uq_user_consents_document"
        ),
    )
    op.create_index(
        "ix_user_consents_user_created", "user_consents", ["user_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_table("user_consents")
    for column in ("request_id", "result", "target_id", "target_type"):
        op.drop_column("audit_logs", column)
    op.drop_column("usage_events", "pricing_version")
    op.drop_column("usage_events", "total_tokens")
    op.drop_constraint("uq_generations_user_message_id", "generations", type_="unique")
    op.drop_constraint("uq_generations_user_client_request", "generations", type_="unique")
    op.drop_constraint("fk_generations_user_id_users", "generations", type_="foreignkey")
    for column in (
        "latency_ms",
        "cancelled_at",
        "started_at",
        "context_truncated",
        "error_detail_redacted",
        "client_request_id",
        "user_id",
    ):
        op.drop_column("generations", column)
    for column in (
        "config_json",
        "pricing_version",
        "output_price_per_million",
        "input_price_per_million",
        "default_output_tokens",
        "context_rounds",
        "sort_order",
        "display_name_i18n",
    ):
        op.drop_column("model_profiles", column)
    for column in ("revoked_at", "absolute_expires_at", "idle_expires_at"):
        op.drop_column("auth_sessions", column)
    op.alter_column("conversations", "title", type_=sa.String(160), existing_type=sa.String(100))
    op.alter_column("users", "locale", type_=sa.String(8), existing_type=sa.String(10))
    op.alter_column("users", "display_name", type_=sa.String(80), existing_type=sa.String(50))
