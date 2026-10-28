"""Durable PostgreSQL queue worker. Run one low-concurrency worker per deployment."""

import asyncio
import json
import os
import sys
import uuid
from datetime import timedelta

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.security import utc_now
from app.db.models import Document, DocumentChunk, DocumentUsage
from app.db.session import SessionLocal
from app.services.document_storage import private_path
from app.services.embeddings import EmbeddingError, embed_texts
from app.services.token_budget import chunk_pages


async def parse_document(item, settings):
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "app.services.document_parser",
        str(private_path(settings, item.storage_key)),
        item.mime_type,
        str(settings.document_pdf_pages),
        str(settings.document_max_chars),
        settings.ocr_languages,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env={
            **{
                key: os.environ[key]
                for key in ("PATH", "PYTHONPATH", "LANG", "LC_ALL", "TESSDATA_PREFIX")
                if key in os.environ
            },
            "OMP_THREAD_LIMIT": "1",
            "OPENBLAS_NUM_THREADS": "1",
        },
        start_new_session=True,
    )
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), settings.document_parse_timeout)
        parsed = json.loads(stdout)
        if process.returncode or parsed.get("error"):
            raise ValueError(parsed.get("error", "Parser failed"))
        return parsed["pages"]
    except TimeoutError:
        raise ValueError("Document processing timed out; use a smaller file") from None
    finally:
        # Kill the entire process group, including an OCR subprocess on timeout/cancellation.
        import signal

        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await process.wait()


async def claim_document(session_factory=SessionLocal, settings=None):
    settings = settings or get_settings()
    async with session_factory() as db:
        stale = utc_now() - timedelta(seconds=660)
        expired = (
            await db.scalars(
                select(Document)
                .where(
                    Document.status == "processing",
                    Document.processing_started_at < stale,
                )
                .with_for_update(skip_locked=True)
            )
        ).all()
        for item in expired:
            item.status, item.error = "failed", "Processing was interrupted; retry the document"
        item = await db.scalar(
            select(Document)
            .where(Document.status == "pending")
            .order_by(Document.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if item:
            item.status, item.progress, item.error = "processing", 10, None
            item.processing_token, item.processing_started_at = uuid.uuid4(), utc_now()
        await db.commit()
        return item


async def process_document(item, session_factory=SessionLocal, settings=None):
    settings = settings or get_settings()
    try:
        async with asyncio.timeout(600):
            pages = await parse_document(item, settings)
            chunks = chunk_pages(pages, settings)
            # Empty visual images remain available for Vision. They do not invent OCR text.
            if not chunks and not item.mime_type.startswith("image/"):
                raise ValueError("No readable text was found")
            vectors = []
            for offset in range(0, len(chunks), 32):
                batch, tokens = await embed_texts(
                    [c["content"] for c in chunks[offset : offset + 32]], settings
                )
                vectors.extend(batch)
                async with session_factory() as db:
                    current = await db.get(Document, item.id, with_for_update=True)
                    if not current or current.processing_token != item.processing_token:
                        return
                    current.progress = 30 + round(60 * len(vectors) / len(chunks))
                    db.add(
                        DocumentUsage(
                            user_id=current.user_id,
                            model=settings.embedding_model,
                            purpose="index",
                            input_tokens=tokens,
                            estimated_cost_microusd=round(
                                tokens * settings.embedding_price_per_million
                            ),
                        )
                    )
                    await db.commit()
            async with session_factory() as db:
                current = await db.get(Document, item.id, with_for_update=True)
                if not current or current.processing_token != item.processing_token:
                    return
                await db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == item.id))
                for ordinal, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
                    db.add(
                        DocumentChunk(
                            document_id=item.id,
                            ordinal=ordinal,
                            **chunk,
                            embedding=vector,
                            embedding_model=settings.embedding_model,
                            embedding_version=settings.embedding_version,
                            embedding_dimensions=settings.embedding_dimensions,
                        )
                    )
                current.page_count = len(pages) if item.mime_type == "application/pdf" else None
                current.embedding_model = settings.embedding_model
                current.embedding_version = settings.embedding_version
                current.embedding_dimensions = settings.embedding_dimensions
                current.status, current.progress = "ready", 100
                await db.commit()
    except Exception as exc:
        async with session_factory() as db:
            current = await db.get(Document, item.id, with_for_update=True)
            if current and current.processing_token == item.processing_token:
                current.status = "failed"
                current.error = (
                    str(exc)
                    if isinstance(exc, (ValueError, EmbeddingError))
                    else "Document processing failed; retry later"
                )[:300]
                await db.commit()


async def main():
    while True:
        try:
            item = await claim_document()
            if item:
                await process_document(item)
            else:
                await asyncio.sleep(2)
        except Exception:
            # A database outage must not kill the queue consumer or expose document text.
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
