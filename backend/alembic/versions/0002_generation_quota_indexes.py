"""Add indexes used by atomic generation quota checks.

Revision ID: 0002_generation_quota_indexes
Revises: 0001_initial
"""

from alembic import op


revision = "0002_generation_quota_indexes"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_generations_conversation_created",
        "generations",
        ["conversation_id", "created_at"],
    )
    op.create_index(
        "ix_generations_conversation_status",
        "generations",
        ["conversation_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_generations_conversation_status", table_name="generations")
    op.drop_index("ix_generations_conversation_created", table_name="generations")
