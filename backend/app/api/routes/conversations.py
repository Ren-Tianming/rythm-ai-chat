import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, time, timedelta
from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, update
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
    User,
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
from app.services.anti_abuse import rate_limiter
from app.services.generation_control import generation_controls
from app.services.llm import (
    LLMMessage,
    ProviderError,
    configured_model_id,
    configured_provider_names,
    estimate_cost_microusd,
)


router = APIRouter(tags=["chat"])
ACTIVE_GENERATION_STATUSES = ("pending", "streaming")


class GenerationCancelled(Exception):
    pass


async def events_with_keepalive(provider, messages, model_id, max_tokens):
    iterator = provider.stream(messages, model_id, max_tokens).__aiter__()
    pending = asyncio.create_task(anext(iterator))
    try:
        while True:
            done, _ = await asyncio.wait({pending}, timeout=15)
            if not done:
                yield None
                continue
            try:
                event = pending.result()
            except StopAsyncIteration:
                return
            yield event
            pending = asyncio.create_task(anext(iterator))
    finally:
        if not pending.done():
            pending.cancel()
        close = getattr(iterator, "aclose", None)
        if close:
            await close()


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
    settings: Settings = Depends(get_settings),
) -> ConversationResponse:
    model = await db.scalar(
        select(ModelProfile).where(
            ModelProfile.id == payload.model_profile_id, ModelProfile.enabled.is_(True)
        )
    )
    if not model:
        raise HTTPException(status_code=400, detail="Model is not available")
    if model.provider not in configured_provider_names(settings):
        raise HTTPException(status_code=400, detail="Model is not configured")
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
    settings: Settings = Depends(get_settings),
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
        if model.provider not in configured_provider_names(settings):
            raise HTTPException(status_code=400, detail="Model is not configured")
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
    await rate_limiter.check(
        f"chat:user:{auth.user.id}", settings.chat_per_minute_limit, 60
    )
    conversation = await get_owned_conversation(conversation_id, auth.user.id, db)
    selected_model_id = payload.model_profile_id or conversation.model_profile_id
    model = await db.scalar(
        select(ModelProfile).where(
            ModelProfile.id == selected_model_id, ModelProfile.enabled.is_(True)
        )
    )
    if not model or model.provider not in configured_provider_names(settings):
        raise HTTPException(status_code=409, detail="Selected model is unavailable")
    duplicate = await db.scalar(
        select(Generation).where(
            Generation.user_id == auth.user.id,
            Generation.client_request_id == payload.client_request_id,
        )
    )
    if duplicate:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DUPLICATE_REQUEST",
                "message": "This message request was already accepted",
                "details": {
                    "generation_id": str(duplicate.id),
                    "status": duplicate.status,
                },
            },
        )

    await db.scalar(select(User.id).where(User.id == auth.user.id).with_for_update())
    now = utc_now()
    stale_before = now - timedelta(seconds=max(settings.generation_timeout_seconds * 2, 300))
    user_conversation_ids = select(Conversation.id).where(Conversation.user_id == auth.user.id)
    await db.execute(
        update(Generation)
        .where(
            Generation.conversation_id.in_(user_conversation_ids),
            Generation.status.in_(ACTIVE_GENERATION_STATUSES),
            Generation.created_at < stale_before,
        )
        .values(
            status="failed",
            error_code="STALE_GENERATION",
            completed_at=now,
        )
    )

    start_today = datetime.combine(datetime.now(UTC).date(), time.min, tzinfo=UTC)
    requests_today = await db.scalar(
        select(func.count(Generation.id))
        .join(Conversation, Conversation.id == Generation.conversation_id)
        .where(
            Conversation.user_id == auth.user.id,
            Generation.created_at >= start_today,
        )
    )
    if (requests_today or 0) >= settings.daily_chat_limit:
        raise HTTPException(status_code=429, detail="Daily chat limit reached")

    active_generations = await db.scalar(
        select(func.count(Generation.id))
        .join(Conversation, Conversation.id == Generation.conversation_id)
        .where(
            Conversation.user_id == auth.user.id,
            Generation.status.in_(ACTIVE_GENERATION_STATUSES),
        )
    )
    if (active_generations or 0) >= settings.max_concurrent_generations_per_user:
        raise HTTPException(
            status_code=429,
            detail="Another generation is already in progress",
        )

    conversation_generation_active = await db.scalar(
        select(func.count(Generation.id)).where(
            Generation.conversation_id == conversation.id,
            Generation.status.in_(ACTIVE_GENERATION_STATUSES),
        )
    )
    if conversation_generation_active:
        raise HTTPException(
            status_code=409,
            detail="This conversation already has a generation in progress",
        )

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
    assistant_message = Message(
        conversation_id=conversation.id,
        sequence_no=user_message.sequence_no + 1,
        role="assistant",
        content="",
        status="streaming",
        model_profile_id=model.id,
    )
    db.add(assistant_message)
    await db.flush()
    generation = Generation(
        user_id=auth.user.id,
        conversation_id=conversation.id,
        client_request_id=payload.client_request_id,
        user_message_id=user_message.id,
        assistant_message_id=assistant_message.id,
        model_profile_id=model.id,
    )
    db.add(generation)
    if (max_sequence or 0) == 0:
        conversation.title = content[:30] + ("…" if len(content) > 30 else "")
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
    candidate_history = select_complete_rounds(
        [ContextMessage(role=item.role, content=item.content) for item in previous_rows],
        min(settings.context_rounds, model.context_rounds, 5),
    )
    budget = max(0, settings.max_context_chars - len(settings.system_prompt) - len(content))
    history: list[ContextMessage] = []
    used_chars = 0
    for index in range(len(candidate_history) - 2, -1, -2):
        pair = candidate_history[index : index + 2]
        pair_chars = sum(len(item.content) for item in pair)
        if used_chars + pair_chars > budget:
            break
        history[0:0] = pair
        used_chars += pair_chars
    generation.context_truncated = len(history) < len(candidate_history)
    await db.commit()

    llm_messages = [LLMMessage(role="system", content=settings.system_prompt)]
    llm_messages.extend(LLMMessage(role=item.role, content=item.content) for item in history)
    llm_messages.append(LLMMessage(role="user", content=content))
    registry = request.app.state.provider_registry
    provider = registry.get(model.provider)
    actual_model_id = configured_model_id(model.provider, model.model_id, settings)
    max_tokens = min(model.max_output_tokens, settings.max_output_tokens, 1024)
    control = generation_controls.register(generation.id)

    async def event_stream() -> AsyncIterator[str]:
        full_text = ""
        input_tokens = 0
        output_tokens = 0
        finish_reason = None
        started = perf_counter()
        try:
            generation.status = "streaming"
            generation.started_at = utc_now()
            await db.commit()
            yield sse(
                "meta",
                {
                    "generation_id": generation.id,
                    "assistant_message_id": assistant_message.id,
                    "model_key": model.slug,
                    "history_rounds": len(history) // 2,
                    "context_truncated": generation.context_truncated,
                },
            )
            async with asyncio.timeout(settings.generation_timeout_seconds):
                attempts = 0
                emitted_delta = False
                while True:
                    try:
                        async for event in events_with_keepalive(
                            provider, llm_messages, actual_model_id, max_tokens
                        ):
                            if control.cancelled.is_set() or await request.is_disconnected():
                                raise GenerationCancelled
                            if event is None:
                                yield ": keepalive\n\n"
                                continue
                            if event.text:
                                emitted_delta = True
                                full_text += event.text
                                yield sse("delta", {"text": event.text})
                            input_tokens = event.input_tokens or input_tokens
                            output_tokens = event.output_tokens or output_tokens
                            finish_reason = event.finish_reason or finish_reason
                            generation.provider_request_id = (
                                event.request_id or generation.provider_request_id
                            )
                        if control.cancelled.is_set() or await request.is_disconnected():
                            raise GenerationCancelled
                        break
                    except ProviderError as exc:
                        if not emitted_delta and attempts < 1 and exc.retryable:
                            attempts += 1
                            await asyncio.sleep(0.5)
                            continue
                        raise
            assistant_message.content = full_text
            assistant_message.status = "completed"
            assistant_message.input_tokens = input_tokens
            assistant_message.output_tokens = output_tokens
            assistant_message.finish_reason = finish_reason
            generation.status = "completed"
            generation.completed_at = utc_now()
            generation.latency_ms = round((perf_counter() - started) * 1000)
            cost = estimate_cost_microusd(
                model.provider,
                actual_model_id,
                input_tokens,
                output_tokens,
                float(model.input_price_per_million)
                if model.input_price_per_million is not None
                else None,
                float(model.output_price_per_million)
                if model.output_price_per_million is not None
                else None,
            )
            db.add(
                UsageEvent(
                    user_id=auth.user.id,
                    generation_id=generation.id,
                    provider=model.provider,
                    model_id=actual_model_id,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=input_tokens + output_tokens,
                    estimated_cost_microusd=cost,
                    pricing_version=model.pricing_version,
                )
            )
            conversation.updated_at = utc_now()
            await db.commit()
            yield sse(
                "usage",
                {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                    "estimated_cost_usd": f"{cost / 1_000_000:.6f}",
                },
            )
            yield sse(
                "done",
                {
                    "message_id": assistant_message.id,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "finish_reason": finish_reason,
                },
            )
        except (GenerationCancelled, asyncio.CancelledError) as exc:
            now = utc_now()
            assistant_message.content = full_text
            assistant_message.status = "cancelled"
            assistant_message.input_tokens = input_tokens
            assistant_message.output_tokens = output_tokens
            assistant_message.finish_reason = "cancelled"
            generation.status = "cancelled"
            generation.cancelled_at = now
            generation.completed_at = now
            generation.latency_ms = round((perf_counter() - started) * 1000)
            await db.commit()
            if isinstance(exc, asyncio.CancelledError):
                raise
            if not await request.is_disconnected():
                yield sse("done", {"finish_reason": "cancelled"})
        except TimeoutError:
            assistant_message.content = full_text
            assistant_message.status = "failed"
            generation.status = "failed"
            generation.error_code = "MODEL_TIMEOUT"
            generation.completed_at = utc_now()
            generation.latency_ms = round((perf_counter() - started) * 1000)
            await db.commit()
            yield sse(
                "error",
                {
                    "code": "MODEL_TIMEOUT",
                    "message": "Generation timed out",
                },
            )
        except ProviderError as exc:
            assistant_message.content = full_text
            assistant_message.status = "failed"
            generation.status = "failed"
            generation.error_code = exc.code
            generation.completed_at = utc_now()
            generation.latency_ms = round((perf_counter() - started) * 1000)
            await db.commit()
            yield sse("error", {"code": exc.code, "message": str(exc)})
        except Exception as exc:
            assistant_message.content = full_text
            assistant_message.status = "failed"
            generation.status = "failed"
            generation.error_code = "INTERNAL_ERROR"
            generation.error_detail_redacted = type(exc).__name__
            generation.completed_at = utc_now()
            generation.latency_ms = round((perf_counter() - started) * 1000)
            await db.commit()
            yield sse("error", {"code": "INTERNAL_ERROR", "message": "Generation failed"})
        finally:
            generation_controls.remove(generation.id)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/generations/{generation_id}/cancel", response_model=MessageResponse)
async def cancel_generation(
    generation_id: uuid.UUID,
    auth: CurrentAuth = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    generation = await db.scalar(
        select(Generation).where(
            Generation.id == generation_id,
            Generation.user_id == auth.user.id,
        )
    )
    if not generation:
        raise HTTPException(status_code=404, detail="Generation not found")
    if generation.status not in ACTIVE_GENERATION_STATUSES:
        return MessageResponse(message=f"Generation is already {generation.status}")
    generation_controls.cancel(generation.id)
    generation.status = "cancelled"
    generation.cancelled_at = utc_now()
    generation.completed_at = generation.cancelled_at
    await db.commit()
    return MessageResponse(message="Generation cancelled")


@router.get("/usage/me", response_model=UsageSummaryResponse)
async def usage_summary(
    auth: CurrentAuth = Depends(get_current_auth),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> UsageSummaryResponse:
    start_today = datetime.combine(datetime.now(UTC).date(), time.min, tzinfo=UTC)
    requests_today = await db.scalar(
        select(func.count(Generation.id))
        .join(Conversation, Conversation.id == Generation.conversation_id)
        .where(
            Conversation.user_id == auth.user.id,
            Generation.created_at >= start_today,
        )
    )
    row = (
        await db.execute(
            select(
                func.coalesce(func.sum(UsageEvent.input_tokens), 0),
                func.coalesce(func.sum(UsageEvent.output_tokens), 0),
                func.coalesce(func.sum(UsageEvent.estimated_cost_microusd), 0),
            ).where(UsageEvent.user_id == auth.user.id, UsageEvent.created_at >= start_today)
        )
    ).one()
    return UsageSummaryResponse(
        requests_today=requests_today or 0,
        daily_limit=settings.daily_chat_limit,
        input_tokens=row[0],
        output_tokens=row[1],
        estimated_cost_microusd=row[2],
    )
