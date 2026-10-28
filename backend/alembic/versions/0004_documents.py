"""Private documents, vector search, retrieval provenance and model output budgets."""

from alembic import op
import sqlalchemy as sa

revision = "0004_documents"
down_revision = "0003_production_baseline"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column(
        "messages",
        sa.Column(
            "continuation_of_id", sa.Uuid(), sa.ForeignKey("messages.id", ondelete="SET NULL")
        ),
    )
    op.execute(
        "CREATE TABLE documents (\n\tid UUID NOT NULL, \n\tuser_id UUID NOT NULL, \n\tconversation_id UUID NOT NULL, \n\tfilename VARCHAR(255) NOT NULL, \n\tstorage_key VARCHAR(80) NOT NULL, \n\tmime_type VARCHAR(80) NOT NULL, \n\tsize_bytes INTEGER NOT NULL, \n\tstatus VARCHAR(16) NOT NULL, \n\tprogress INTEGER NOT NULL, \n\terror VARCHAR(300), \n\tpage_count INTEGER, \n\tembedding_model VARCHAR(160), \n\tembedding_version VARCHAR(160), \n\tembedding_dimensions INTEGER, \n\tprocessing_token UUID, \n\tprocessing_started_at TIMESTAMP WITH TIME ZONE, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCHECK (status IN ('pending','processing','ready','failed')), \n\tFOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, \n\tFOREIGN KEY(conversation_id) REFERENCES conversations (id) ON DELETE CASCADE, \n\tUNIQUE (storage_key)\n)"
    )
    op.execute(
        "CREATE INDEX ix_documents_owner_conversation ON documents (user_id, conversation_id)"
    )
    op.execute("CREATE INDEX ix_documents_queue ON documents (status, created_at)")
    op.execute(
        "CREATE TABLE document_chunks (\n\tid UUID NOT NULL, \n\tdocument_id UUID NOT NULL, \n\tordinal INTEGER NOT NULL, \n\tpage_number INTEGER, \n\tcontent TEXT NOT NULL, \n\ttoken_count INTEGER NOT NULL, \n\tembedding VECTOR NOT NULL, \n\tembedding_model VARCHAR(160) NOT NULL, \n\tembedding_version VARCHAR(160) NOT NULL, \n\tembedding_dimensions INTEGER NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE\n)"
    )
    op.execute("CREATE INDEX ix_document_chunks_document ON document_chunks (document_id)")
    op.execute(
        "CREATE TABLE message_sources (\n\tid UUID NOT NULL, \n\tmessage_id UUID NOT NULL, \n\tdocument_id UUID NOT NULL, \n\tchunk_id UUID, \n\tsource_kind VARCHAR(16) NOT NULL, \n\tlabel VARCHAR(16) NOT NULL, \n\texcerpt TEXT NOT NULL, \n\tsimilarity NUMERIC(8, 6) NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(message_id) REFERENCES messages (id) ON DELETE CASCADE, \n\tFOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE, \n\tFOREIGN KEY(chunk_id) REFERENCES document_chunks (id) ON DELETE CASCADE\n)"
    )
    op.execute("CREATE INDEX ix_message_sources_message ON message_sources (message_id)")
    op.execute(
        "CREATE TABLE document_usage (\n\tid UUID NOT NULL, \n\tuser_id UUID NOT NULL, \n\tmodel VARCHAR(160) NOT NULL, \n\tpurpose VARCHAR(16) NOT NULL, \n\tinput_tokens INTEGER NOT NULL, \n\testimated_cost_microusd BIGINT NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE\n)"
    )
    # Migrate old short defaults; preserve explicit administrator budgets.
    op.execute(
        "UPDATE model_profiles SET max_output_tokens = 8192, default_output_tokens = 8192 WHERE max_output_tokens = 512 AND default_output_tokens = 512 AND slug IN ('deepseek-v4-flash','gemini-3-1-flash-lite','groq-gpt-oss-20b')"
    )
    op.execute(
        "UPDATE model_profiles SET config_json = jsonb_set(config_json::jsonb, '{supports_vision}', 'true')::json WHERE model_id = 'gemini-3.1-flash-lite' AND NOT config_json::jsonb ? 'supports_vision'"
    )
    op.alter_column("model_profiles", "max_output_tokens", server_default="8192")
    op.alter_column("model_profiles", "default_output_tokens", server_default="8192")


def downgrade():
    for name in ("document_usage", "message_sources", "document_chunks", "documents"):
        op.drop_table(name)
    op.drop_column("messages", "continuation_of_id")
    op.alter_column("model_profiles", "max_output_tokens", server_default="512")
    op.alter_column("model_profiles", "default_output_tokens", server_default="512")
    # Keep the shared extension and administrator budgets.
