import os
import uuid
from datetime import timedelta
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings, get_settings
from app.core.security import hash_password, token_digest, utc_now
from app.db.base import Base
from app.db.models import AuthSession, Conversation, ModelProfile, User
from app.db.session import get_db
from app.main import create_app
from app.services.llm.base import ProviderEvent


def vectorize(value):
    value = value.casefold()
    if any(k in value for k in ("orion", "オリオン", "猎户", "4200000", "budget", "予算", "预算")):
        return [1.0, 0, 0, 0, 0, 0, 0, 0]
    if any(k in value for k in ("banana", "バナナ", "香蕉")):
        return [0, 1.0, 0, 0, 0, 0, 0, 0]
    return [0, 0, 1.0, 0, 0, 0, 0, 0]


async def fake_embeddings(texts, settings):
    return [vectorize(value) for value in texts], sum(len(value) for value in texts)


class FakeProvider:
    def __init__(self):
        self.calls = []

    async def stream(self, messages, model_id, max_tokens):
        self.calls.append((messages, model_id, max_tokens))
        question = messages[-1].content
        if "LONG" in question:
            yield ProviderEvent(
                text="word " * 1500, input_tokens=30, output_tokens=1500, finish_reason="length"
            )
        else:
            yield ProviderEvent(
                text="Document evidence: ORION budget is 4200000 yen. [S1]",
                input_tokens=50,
                output_tokens=20,
                finish_reason="stop",
            )

    async def aclose(self):
        pass


@pytest_asyncio.fixture
async def system(tmp_path, monkeypatch):
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL/pgvector integration tests")
    schema = f"test_{uuid.uuid4().hex}"
    admin = create_async_engine(database_url)
    async with admin.begin() as connection:
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await connection.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_async_engine(
        database_url, connect_args={"server_settings": {"search_path": f"{schema},public"}}
    )
    async with engine.begin() as connection:
        await connection.run_sync(lambda bind: Base.metadata.create_all(bind, checkfirst=False))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        _env_file=None,
        environment="test",
        upload_dir=str(tmp_path / "uploads"),
        deepseek_api_key="test-only",
        deepseek_model="test-model",
        groq_api_key="test-only",
        groq_model="test-model-2",
        embedding_api_key="test-only",
        embedding_dimensions=8,
        ocr_languages=os.getenv("OCR_LANGUAGES", "eng"),
        chat_per_minute_limit=100,
        daily_chat_limit=1000,
    )
    async with factory() as db:
        users, conversations, cookies = [], [], []
        model = ModelProfile(
            slug="test",
            provider="deepseek",
            display_name="Test model",
            model_id="test-model",
            description_key="models.deepseek",
            is_default=True,
            config_json={"context_window_tokens": 65536},
        )
        second_model = ModelProfile(
            slug="test-2",
            provider="groq",
            display_name="Second model",
            model_id="test-model-2",
            description_key="models.groq",
        )
        db.add_all([model, second_model])
        await db.flush()
        for index in range(2):
            user = User(
                email=f"user{index}@example.com",
                normalized_email=f"user{index}@example.com",
                password_hash=hash_password("Secure_Test_Pass_2026!"),
                status="active",
                email_verified_at=utc_now(),
                locale="en-US",
            )
            db.add(user)
            await db.flush()
            token, csrf = f"test-session-{index}", f"test-csrf-{index}"
            db.add(
                AuthSession(
                    user_id=user.id,
                    token_hash=token_digest(token, settings.app_secret),
                    csrf_hash=token_digest(csrf, settings.app_secret),
                    expires_at=utc_now() + timedelta(days=1),
                    idle_expires_at=utc_now() + timedelta(days=1),
                    absolute_expires_at=utc_now() + timedelta(days=1),
                )
            )
            conversation = Conversation(user_id=user.id, model_profile_id=model.id)
            db.add(conversation)
            users.append(user)
            conversations.append(conversation)
            cookies.append({"rythm_session": token, "rythm_csrf": csrf})
        await db.commit()
    app = create_app()

    async def database():
        async with factory() as db:
            yield db

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_settings] = lambda: settings
    provider = FakeProvider()
    monkeypatch.setattr("app.services.rag.embed_texts", fake_embeddings)
    monkeypatch.setattr("app.services.document_worker.embed_texts", fake_embeddings)
    from app.services.anti_abuse import rate_limiter

    rate_limiter._events.clear()
    try:
        async with app.router.lifespan_context(app):
            app.state.provider_registry.providers["deepseek"] = provider
            app.state.provider_registry.providers["groq"] = provider
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
                cookies=cookies[0],
                headers={"X-CSRF-Token": cookies[0]["rythm_csrf"]},
            ) as client:
                yield SimpleNamespace(
                    client=client,
                    app=app,
                    settings=settings,
                    factory=factory,
                    users=users,
                    conversations=conversations,
                    cookies=cookies,
                    model=model,
                    second_model=second_model,
                    provider=provider,
                )
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        await admin.dispose()
