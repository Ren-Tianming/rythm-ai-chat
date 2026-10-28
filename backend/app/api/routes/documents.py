import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile

from app.api.deps import CurrentAuth, get_current_auth, require_csrf
from app.core.config import Settings, get_settings
from app.db.models import Conversation, Document, DocumentChunk, MessageSource, User
from app.db.session import get_db
from app.services.anti_abuse import rate_limiter
from app.services.document_storage import private_path, validate_upload

router = APIRouter(tags=["documents"])


async def owned_conversation(conversation_id, user_id, db):
    item = await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
            Conversation.deleted_at.is_(None),
        )
    )
    if not item:
        raise HTTPException(404, "Conversation not found")
    return item


async def owned_document(document_id, user_id, db, lock=False):
    query = (
        select(Document)
        .join(Conversation)
        .where(
            Document.id == document_id,
            Document.user_id == user_id,
            Conversation.user_id == user_id,
            Conversation.deleted_at.is_(None),
        )
    )
    if lock:
        query = query.with_for_update(of=Document)
    item = await db.scalar(query)
    if not item:
        raise HTTPException(404, "Document not found")
    return item


def metadata(item, settings):
    return {
        "id": str(item.id),
        "conversation_id": str(item.conversation_id),
        "filename": item.filename,
        "mime_type": item.mime_type,
        "size_bytes": item.size_bytes,
        "status": item.status,
        "progress": item.progress,
        "error": item.error,
        "page_count": item.page_count,
        "created_at": item.created_at,
        "embedding_version": item.embedding_version,
        "requires_reindex": item.status == "ready"
        and (
            item.embedding_model != settings.embedding_model
            or item.embedding_version != settings.embedding_version
            or item.embedding_dimensions != settings.embedding_dimensions
        ),
    }


@router.post("/conversations/{conversation_id}/documents", status_code=202)
async def upload_documents(
    conversation_id: uuid.UUID,
    request: Request,
    auth: CurrentAuth = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    await rate_limiter.check(f"upload:{auth.user.id}", 10, 60)
    await db.scalar(select(User.id).where(User.id == auth.user.id).with_for_update())
    await owned_conversation(conversation_id, auth.user.id, db)
    count, used = (
        await db.execute(
            select(func.count(Document.id), func.coalesce(func.sum(Document.size_bytes), 0)).where(
                Document.user_id == auth.user.id
            )
        )
    ).one()
    created = []
    try:
        async with request.form(max_files=settings.document_batch_limit, max_fields=0) as form:
            files = form.getlist("files")
            if (
                not 1 <= len(files) <= settings.document_batch_limit
                or any(not isinstance(f, UploadFile) for f in files)
                or len(form.multi_items()) != len(files)
            ):
                raise HTTPException(
                    422, f"Upload 1–{settings.document_batch_limit} files using the files field"
                )
            if count + len(files) > settings.document_user_limit:
                raise HTTPException(413, f"User file count limit: {settings.document_user_limit}")
            for file in files:
                data = await file.read(settings.document_max_bytes + 1)
                if len(data) > settings.document_max_bytes:
                    raise HTTPException(413, f"File exceeds {settings.document_max_bytes} bytes")
                used += len(data)
                if used > settings.document_user_bytes:
                    raise HTTPException(
                        413, f"User storage limit: {settings.document_user_bytes} bytes"
                    )
                name, mime, key = await asyncio.to_thread(
                    validate_upload, file.filename or "", data
                )
                item = Document(
                    user_id=auth.user.id,
                    conversation_id=conversation_id,
                    filename=name,
                    mime_type=mime,
                    storage_key=key,
                    size_bytes=len(data),
                    status="pending",
                )
                path = private_path(settings, key)
                path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                # Exclusive creation and fixed internal paths prevent overwrite/path traversal.
                with path.open("xb") as handle:
                    created.append(path)
                    handle.write(data)
                path.chmod(0o600)
                db.add(item)
            await db.flush()
            rows = (
                await db.scalars(
                    select(Document).where(Document.storage_key.in_([p.name for p in created]))
                )
            ).all()
            result = [metadata(item, settings) for item in rows]
            await db.commit()
            return result
    except BaseException:
        await db.rollback()
        for path in created:
            path.unlink(missing_ok=True)
        raise


@router.get("/conversations/{conversation_id}/documents")
async def list_documents(
    conversation_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    await owned_conversation(conversation_id, auth.user.id, db)
    rows = (
        await db.scalars(
            select(Document)
            .where(Document.conversation_id == conversation_id, Document.user_id == auth.user.id)
            .order_by(Document.created_at)
        )
    ).all()
    return [metadata(item, settings) for item in rows]


@router.get("/documents/limits")
async def document_limits(
    auth: CurrentAuth = Depends(get_current_auth), settings: Settings = Depends(get_settings)
):
    return {
        "max_bytes": settings.document_max_bytes,
        "batch_limit": settings.document_batch_limit,
        "user_limit": settings.document_user_limit,
        "user_bytes": settings.document_user_bytes,
        "pdf_pages": settings.document_pdf_pages,
    }


@router.get("/documents/{document_id}")
async def get_document(
    document_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    item = await owned_document(document_id, auth.user.id, db)
    result = metadata(item, settings)
    # Bound preview; the original remains available without truncation as a download.
    chunks = (
        await db.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == item.id)
            .order_by(DocumentChunk.ordinal)
            .limit(3)
        )
    ).all()
    result["preview"] = [{"page_number": c.page_number, "content": c.content} for c in chunks]
    result["preview_limited"] = True
    return result


@router.get("/documents/{document_id}/content")
async def document_content(
    document_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    item = await owned_document(document_id, auth.user.id, db)
    path = private_path(settings, item.storage_key)
    if not path.is_file():
        raise HTTPException(404, "Original file is unavailable")
    return FileResponse(
        path,
        media_type=item.mime_type,
        filename=item.filename,
        content_disposition_type="inline" if item.mime_type.startswith("image/") else "attachment",
        headers={
            "Cache-Control": "private, no-store",
            "Content-Security-Policy": "sandbox; default-src 'none'",
            "X-Content-Type-Options": "nosniff",
        },
    )


async def remove_document(item, db, settings):
    # Explicit cleanup also covers SQLite tests where foreign keys may be disabled.
    private_path(settings, item.storage_key).unlink(missing_ok=True)
    await db.execute(delete(MessageSource).where(MessageSource.document_id == item.id))
    await db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == item.id))
    await db.delete(item)


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(
    document_id: uuid.UUID,
    auth: CurrentAuth = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    await db.scalar(select(User.id).where(User.id == auth.user.id).with_for_update())
    item = await owned_document(document_id, auth.user.id, db, lock=True)
    await remove_document(item, db, settings)
    await db.commit()


@router.post("/documents/{document_id}/retry", status_code=202)
async def retry_document(
    document_id: uuid.UUID,
    auth: CurrentAuth = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    await rate_limiter.check(f"upload:{auth.user.id}", 10, 60)
    item = await owned_document(document_id, auth.user.id, db, lock=True)
    if item.status not in ("failed", "ready"):
        raise HTTPException(409, "Document is already queued or processing")
    await db.execute(delete(MessageSource).where(MessageSource.document_id == item.id))
    await db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == item.id))
    item.status, item.progress, item.error, item.processing_token = "pending", 0, None, None
    await db.commit()
    return metadata(item, settings)
