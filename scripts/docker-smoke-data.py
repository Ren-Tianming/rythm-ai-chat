"""Disposable Compose smoke data; executed inside the backend image via stdin."""

import asyncio
import sys
import uuid
from pathlib import Path

from app.core.config import get_settings
from app.db.models import (
    Conversation,
    Document,
    DocumentChunk,
    Message,
    MessageSource,
    ModelProfile,
    User,
)
from app.db.session import SessionLocal
from sqlalchemy import select

key = "a" * 32 + ".txt"
expected = "Private ORION backup evidence."


async def main():
    settings = get_settings()
    path = Path(settings.upload_dir) / key
    async with SessionLocal() as db:
        if sys.argv[1] == "seed":
            user = User(
                email="docker@example.com",
                normalized_email="docker@example.com",
                password_hash="test-only",
                status="active",
            )
            db.add(user)
            await db.flush()
            model = await db.scalar(select(ModelProfile))
            conversation = Conversation(user_id=user.id, model_profile_id=model.id)
            db.add(conversation)
            await db.flush()
            document = Document(
                user_id=user.id,
                conversation_id=conversation.id,
                filename="backup.txt",
                storage_key=key,
                mime_type="text/plain",
                size_bytes=len(expected),
                status="ready",
                progress=100,
                embedding_model=settings.embedding_model,
                embedding_version=settings.embedding_version,
                embedding_dimensions=8,
            )
            message = Message(
                conversation_id=conversation.id,
                sequence_no=1,
                role="assistant",
                content="Fixture evidence [S1]",
                status="completed",
            )
            db.add_all([document, message])
            await db.flush()
            chunk = DocumentChunk(
                document_id=document.id,
                ordinal=0,
                page_number=None,
                content=expected,
                token_count=8,
                embedding=[1.0] + [0.0] * 7,
                embedding_model=settings.embedding_model,
                embedding_version=settings.embedding_version,
                embedding_dimensions=8,
            )
            db.add(chunk)
            await db.flush()
            db.add(
                MessageSource(
                    message_id=message.id,
                    document_id=document.id,
                    chunk_id=chunk.id,
                    label="S1",
                    excerpt=expected,
                    source_kind="retrieval",
                    similarity=1,
                )
            )
            path.write_text(expected)
            await db.commit()
        elif sys.argv[1] == "mutate":
            path.write_text("mutated after backup")
        else:
            assert path.read_text() == expected
            doc = await db.scalar(select(Document).where(Document.storage_key == key))
            chunk = await db.scalar(
                select(DocumentChunk).where(DocumentChunk.document_id == doc.id)
            )
            source = await db.scalar(
                select(MessageSource).where(MessageSource.document_id == doc.id)
            )
            assert (
                chunk.content == expected and list(chunk.embedding) == [1.0] + [0.0] * 7
            )
            assert source.excerpt == expected
            assert doc.user_id and doc.conversation_id and isinstance(doc.id, uuid.UUID)
            print(
                "Private file, document metadata, pgvector and source relationship restored"
            )


asyncio.run(main())
