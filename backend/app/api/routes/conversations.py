import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentAuth, get_current_auth, require_csrf
from app.core.config import Settings, get_settings
from app.core.security import utc_now
from app.db.models import (
    Conversation,
    Generation,
    Message,
    ModelProfile,
    UsageEvent,
)
from app.db.session import get_db
from app.schemas.chat import (
    ChatMessageResponse,
    ConversationCreate,
    ConversationResponse,
    ConversationUpdate,
    SendMessageRequest,
    UsageSummaryResponse,
)
from app.schemas.auth import MessageResponse
from app.services.context import ContextMessage, select_complete_rounds
from app.services.llm import (
    LLMMessage,
    ProviderError,
    ProviderRegistry,
    estimate_cost_microusd,
)


router = APIRouter(tags=["chat"])


def conversation_response(item: Conversation) -> ConversationResponse:
    return ConversationResponse(
        id=item.id,
        title=item.title,
        model_profile_id=item.model_profile_id,
        archived=item.archived,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


async def get_owned_conversation(
    conversation_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession
) -> Conversation:
    item = await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
            Conversation.deleted_at.is_(None),
        )
    )
    if not item:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return item


@router.post("/conversations", response_model=ConversationResponse, status_code=201)
async def create_conversation(
    payload: ConversationCreate,
    auth: CurrentAuth = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    model = await db.scalar(
        select(ModelProfile).where(
            ModelProfile.id == payload.model_profile_id, ModelProfile.enabled.is_(True)
        )
    )
    if not model:
        raise HTTPException(status_code=400, detail="Model is not available")
    item = Conversation(user_id=auth.user.id, model_profile_id=model.id)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return conversation_response(item)


@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    archived: bool = False,
    auth: CurrentAuth = Depends(get_current_auth),
    db: AsyncSession = Depends(get_db),
) -> list[ConversationResponse]:
    items = (
        await db.scalars(
            select(Conversation)
            .where(
                Conversation.user_id == auth.user.id,
                Conversation.deleted_at.is_(None),
                Conversation.archived.is_(archived),
            )
            .order_by(Conversation.updated_at.desc())
            .limit(100)
        )
    ).all()
    return [conversation_response(item) for item in items]


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    return conversation_response(await get_owned_conversation(conversation_id, auth.user.id, db))


@router.patch("/conversations/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: uuid.UUID,
    payload: ConversationUpdate,
    auth: CurrentAuth = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    item = await get_owned_conversation(conversation_id, auth.user.id, db)
    if payload.model_profile_id is not None:
        model = await db.scalar(
            select(ModelProfile).where(
                ModelProfile.id == payload.model_profile_id, ModelProfile.enabled.is_(True)
            )
        )
        if not model:
            raise HTTPException(status_code=400, detail="Model is not available")
        item.model_profile_id = model.id
    if payload.title is not None:
        item.title = payload.title.strip()
    if payload.archived is not None:
        item.archived = payload.archived
    await db.commit()
    return conversation_response(item)


@router.delete("/conversations/{conversation_id}", response_model=MessageResponse)
async def delete_conversation(
    conversation_id: uuid.UUID,
    auth: CurrentAuth = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    item = await get_owned_conversation(conversation_id, auth.user.id, db)
    item.deleted_at = utc_now()
    await db.commit()
    return MessageResponse(message="Conversation deleted")


@router.get(
    "/conversations/{conversation_id}/messages", response_model=list[ChatMessageResponse]
)
async def list_messages(
    conversation_id: uuid.UUID,
    before_sequence: int | None = None,
    limit: int = 50,
    auth: CurrentAuth = Depends(get_current_auth),
    db: AsyncSession = Depends(get_db),
) -> list[ChatMessageResponse]:
    await get_owned_conversation(conversation_id, auth.user.id, db)
    query = select(Message).where(Message.conversation_id == conversation_id)
    if before_sequence is not None:
        query = query.where(Message.sequence_no < before_sequence)
    items = (
        await db.scalars(query.order_by(Message.sequence_no.desc()).limit(min(limit, 100)))
    ).all()
    return [
        ChatMessageResponse(
            id=item.id,
            sequence_no=item.sequence_no,
            role=item.role,
            content=item.content,
            status=item.status,
            model_profile_id=item.model_profile_id,
            input_tokens=item.input_tokens,
            output_tokens=item.output_tokens,
            created_at=item.created_at,
        )
        for item in reversed(items)
    ]


def sse(event: str, data: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.post("/conversations/{conversation_id}/messages/stream")
async def stream_message(
    conversation_id: uuid.UUID,
    payload: SendMessageRequest,
    request: Request,
    auth: CurrentAuth = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="Message cannot be empty")
    if len(content) > settings.max_input_chars:
        raise HTTPException(status_code=422, detail="Message is too long")
    conversation = await get_owned_conversation(conversation_id, auth.user.id, db)
    model = await db.scalar(
        select(ModelProfile).where(
            ModelProfile.id == conversation.model_profile_id, ModelProfile.enabled.is_(True)
        )
    )
    if not model:
        raise HTTPException(status_code=409, detail="Selected model is unavailable")

    start_today = datetime.combine(datetime.now(UTC).date(), time.min, tzinfo=UTC)
    requests_today = await db.scalar(
        select(func.count(UsageEvent.id)).where(
            UsageEvent.user_id == auth.user.id, UsageEvent.created_at >= start_today
        )
    )
    if (requests_today or 0) >= settings.daily_chat_limit:
        raise HTTPException(status_code=429, detail="Daily chat limit reached")

    max_sequence = await db.scalar(
        select(func.max(Message.sequence_no)).where(Message.conversation_id == conversation.id)
    )
    user_message = Message(
        conversation_id=conversation.id,
        sequence_no=(max_sequence or 0) + 1,
        role="user",
        content=content,
        status="completed",
    )
    db.add(user_message)
    await db.flush()
    generation = Generation(
        conversation_id=conversation.id,
        user_message_id=user_message.id,
        model_profile_id=model.id,
    )
    db.add(generation)
    if (max_sequence or 0) == 0:
        conversation.title = content[:60] + ("…" if len(content) > 60 else "")
    conversation.updated_at = utc_now()
    await db.commit()

    previous_rows = (
        await db.scalars(
            select(Message)
            .where(
                Message.conversation_id == conversation.id,
                Message.sequence_no < user_message.sequence_no,
                Message.status == "completed",
            )
            .order_by(Message.sequence_no.asc())
        )
    ).all()
    history = select_complete_rounds(
        [ContextMessage(role=item.role, content=item.content) for item in previous_rows],
        settings.context_rounds,
    )
    llm_messages = [LLMMessage(role="system", content=settings.system_prompt)]
    llm_messages.extend(LLMMessage(role=item.role, content=item.content) for item in history)
    llm_messages.append(LLMMessage(role="user", content=content))
    registry = ProviderRegistry(settings)
    provider = registry.get(model.provider)

    async def event_stream() -> AsyncIterator[str]:
        full_text = ""
        input_tokens = 0
        output_tokens = 0
        finish_reason = None
        try:
            generation.status = "streaming"
            await db.commit()
            yield sse(
                "metadata",
                {
                    "generation_id": generation.id,
                    "model": model.display_name,
                    "history_rounds": settings.context_rounds,
                },
            )
            async for event in provider.stream(
                llm_messages,
                model.model_id,
                min(model.max_output_tokens, settings.max_output_tokens),
            ):
                if await request.is_disconnected():
                    generation.status = "cancelled"
                    generation.completed_at = utc_now()
                    await db.commit()
                    return
                if event.text:
                    full_text += event.text
                    yield sse("delta", {"text": event.text})
                input_tokens = event.input_tokens or input_tokens
                output_tokens = event.output_tokens or output_tokens
                finish_reason = event.finish_reason or finish_reason
                generation.provider_request_id = event.request_id or generation.provider_request_id
            assistant = Message(
                conversation_id=conversation.id,
                sequence_no=user_message.sequence_no + 1,
                role="assistant",
                content=full_text,
                status="completed",
                model_profile_id=model.id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                finish_reason=finish_reason,
            )
            db.add(assistant)
            await db.flush()
            generation.assistant_message_id = assistant.id
            generation.status = "completed"
            generation.completed_at = utc_now()
            cost = estimate_cost_microusd(
                model.provider, model.model_id, input_tokens, output_tokens
            )
            db.add(
                UsageEvent(
                    user_id=auth.user.id,
                    generation_id=generation.id,
                    provider=model.provider,
                    model_id=model.model_id,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    estimated_cost_microusd=cost,
                )
            )
            conversation.updated_at = utc_now()
            await db.commit()
            yield sse(
                "done",
                {
                    "message_id": assistant.id,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "finish_reason": finish_reason,
                },
            )
        except ProviderError as exc:
            generation.status = "failed"
            generation.error_code = exc.code
            generation.completed_at = utc_now()
            await db.commit()
            yield sse("error", {"code": exc.code, "message": str(exc)})
        except Exception:
            generation.status = "failed"
            generation.error_code = "internal_error"
            generation.completed_at = utc_now()
            await db.commit()
            yield sse("error", {"code": "internal_error", "message": "Generation failed"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/usage/me", response_model=UsageSummaryResponse)
async def usage_summary(
    auth: CurrentAuth = Depends(get_current_auth),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> UsageSummaryResponse:
    start_today = datetime.combine(datetime.now(UTC).date(), time.min, tzinfo=UTC)
    row = (
        await db.execute(
            select(
                func.count(UsageEvent.id),
                func.coalesce(func.sum(UsageEvent.input_tokens), 0),
                func.coalesce(func.sum(UsageEvent.output_tokens), 0),
                func.coalesce(func.sum(UsageEvent.estimated_cost_microusd), 0),
            ).where(UsageEvent.user_id == auth.user.id, UsageEvent.created_at >= start_today)
        )
    ).one()
    return UsageSummaryResponse(
        requests_today=row[0],
        daily_limit=settings.daily_chat_limit,
        input_tokens=row[1],
        output_tokens=row[2],
        estimated_cost_microusd=row[3],
    )
