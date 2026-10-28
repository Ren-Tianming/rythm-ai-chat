"""Test-only server: real auth/storage/OCR/pgvector; deterministic AI fixtures.

Requires TEST_DATABASE_URL and ENVIRONMENT=test. Never included in the runtime image.
"""

import asyncio
import contextlib
import json
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
import app.services.document_worker as worker
import app.services.rag as rag
import app.api.routes.auth as auth
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import ModelProfile
from app.db.session import get_db
from app.main import create_app
from app.services.llm.base import ProviderEvent
from app.services.document_worker import claim_document, process_document
from conftest import fake_embeddings

if os.getenv("ENVIRONMENT") != "test" or not os.getenv("TEST_DATABASE_URL"):
    raise RuntimeError(
        "This fixture requires an explicit disposable TEST_DATABASE_URL and ENVIRONMENT=test"
    )

settings = get_settings()
app = create_app()
schema = f"browser_{uuid.uuid4().hex}"
engine = create_async_engine(
    os.environ["TEST_DATABASE_URL"],
    connect_args={"server_settings": {"search_path": f"{schema},public"}},
)
factory = async_sessionmaker(engine, expire_on_commit=False)


async def database():
    async with factory() as db:
        yield db


app.dependency_overrides[get_db] = database

# Replacing imports is confined to this test process, never controlled by HTTP input.
worker.embed_texts = fake_embeddings
rag.embed_texts = fake_embeddings


async def capture_mail(email, token, settings):
    Path(os.environ["E2E_MAIL_FILE"]).write_text(json.dumps({"email": email, "token": token}))


auth.send_verification_email = capture_mail


class BrowserProvider:
    async def stream(self, messages, model_id, max_tokens):
        value = messages[-1].content
        if value.startswith("LONG"):
            for _ in range(30):
                yield ProviderEvent(text="word " * 50)
                await asyncio.sleep(0.01)
            yield ProviderEvent(finish_reason="length", input_tokens=50, output_tokens=1500)
        elif value.startswith("SLOW"):
            for _ in range(60):
                yield ProviderEvent(text="partial response ")
                await asyncio.sleep(0.15)
            yield ProviderEvent(finish_reason="stop")
        elif "Untrusted retrieved evidence" in value:
            yield ProviderEvent(
                text="Document evidence: ORION budget is 4200000 yen. [S1]\n\nInference from documents: a budget is allocated.\n\nGeneral knowledge: budgets should be reviewed.",
                finish_reason="stop",
                input_tokens=100,
                output_tokens=40,
            )
        else:
            yield ProviderEvent(
                text="A complete ordinary chat response.",
                finish_reason="stop",
                input_tokens=20,
                output_tokens=10,
            )

    async def aclose(self):
        pass


async def consume():
    while True:
        item = await claim_document(factory, settings)
        if item:
            await process_document(item, factory, settings)
        else:
            await asyncio.sleep(0.15)


original_lifespan = app.router.lifespan_context


@asynccontextmanager
async def lifespan(instance):
    admin = create_async_engine(os.environ["TEST_DATABASE_URL"])
    async with admin.begin() as connection:
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await connection.execute(text(f"CREATE SCHEMA {schema}"))
    async with engine.begin() as connection:
        await connection.run_sync(lambda bind: Base.metadata.create_all(bind, checkfirst=False))
    async with factory() as db:
        for provider, title in [("deepseek", "Test Chat"), ("groq", "Test Vision")]:
            db.add(
                ModelProfile(
                    slug=provider,
                    provider=provider,
                    display_name=title,
                    model_id="test",
                    description_key=f"models.{provider}",
                    is_default=provider == "deepseek",
                    config_json={
                        "supports_vision": provider == "groq",
                        "context_window_tokens": 65536,
                    },
                )
            )
        await db.commit()
    async with original_lifespan(instance):
        instance.state.provider_registry.providers["deepseek"] = BrowserProvider()
        instance.state.provider_registry.providers["groq"] = BrowserProvider()
        consumer = asyncio.create_task(consume())
        try:
            yield
        finally:
            consumer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await consumer
    await engine.dispose()
    async with admin.begin() as connection:
        await connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
    await admin.dispose()


app.router.lifespan_context = lifespan

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
