import asyncio
import uuid
from types import SimpleNamespace

import httpx
import pytest

from app.core.config import Settings
from app.services.document_storage import private_path, validate_upload
from app.services.embeddings import EmbeddingError, embed_texts
from app.services.llm.base import LLMMessage, OpenAICompatibleProvider
from app.services.llm.gemini import GeminiProvider
from app.services.token_budget import chunk_pages, count_tokens, output_budget


def test_chunking_multilingual_page_provenance_and_overlap():
    settings = Settings(_env_file=None)
    text = "# 日本語・中文・English\n\nこれは文書です。测试内容。 This is evidence.\n\n" * 200
    chunks = chunk_pages([{"page": 1, "text": text}, {"page": 2, "text": "Second page"}], settings)
    assert len(chunks) > 2 and chunks[-1]["page_number"] == 2
    assert all("\ufffd" not in c["content"] for c in chunks)
    assert all(c["token_count"] <= 803 for c in chunks)
    assert chunks[0]["content"][-30:] in chunks[1]["content"]
    assert count_tokens(text) > 1024


def test_budget_depends_on_model_context_and_cost():
    settings = Settings(_env_file=None)
    model = SimpleNamespace(
        max_output_tokens=16000,
        default_output_tokens=12000,
        config_json={"context_window_tokens": 16000},
        input_price_per_million=1,
        output_price_per_million=2,
    )
    assert output_budget(model, settings, [LLMMessage("user", "x" * 10000)]) < 6000
    model.config_json = {"context_window_tokens": 64000}
    assert output_budget(model, settings, []) == 12000
    model.config_json["max_generation_cost_usd"] = 0.005
    assert output_budget(model, settings, []) == 2500
    settings.max_output_tokens = 2048
    assert output_budget(model, settings, []) == 2048
    with pytest.raises(ValueError):
        output_budget(model, settings, [LLMMessage("user", "x" * 65000)])


def test_storage_never_uses_client_paths(tmp_path):
    settings = Settings(_env_file=None, upload_dir=str(tmp_path))
    name, mime, key = validate_upload("../../secret.txt", b"valid text")
    assert name == "secret.txt" and mime == "text/plain"
    assert private_path(settings, key).parent == tmp_path
    for key in ("../../secret", "/etc/passwd", str(uuid.uuid4()), "x.txt"):
        with pytest.raises(ValueError):
            private_path(settings, key)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["openai", "gemini"])
async def test_provider_sends_images_and_long_output_budget(kind):
    import json

    seen = []

    async def handler(request):
        seen.append(json.loads(request.content))
        if kind == "openai":
            return httpx.Response(
                200,
                text='data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"length"}]}\n\n',
            )
        return httpx.Response(
            200,
            text='data: {"candidates":[{"content":{"parts":[{"text":"ok"}]},"finishReason":"MAX_TOKENS"}]}\n\n',
        )

    provider = (
        OpenAICompatibleProvider(
            api_key="test", base_url="https://test", timeout=10, provider="Test"
        )
        if kind == "openai"
        else GeminiProvider(api_key="test", base_url="https://test", timeout=10)
    )
    await provider.client.aclose()
    provider.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    events = [
        e
        async for e in provider.stream(
            [LLMMessage("user", "image", images=[{"mime_type": "image/png", "data": "test"}])],
            "model",
            8192,
        )
    ]
    assert events[0].text == "ok"
    if kind == "openai":
        assert seen[0]["max_tokens"] == 8192
        assert seen[0]["messages"][0]["content"][1]["type"] == "image_url"
    else:
        assert seen[0]["generationConfig"]["maxOutputTokens"] == 8192
        assert seen[0]["contents"][0]["parts"][1]["inlineData"]["mimeType"] == "image/png"
    await provider.aclose()


@pytest.mark.asyncio
async def test_cancel_closes_upstream_iterator_promptly():
    from app.api.routes.conversations import events_with_keepalive, GenerationCancelled
    from app.services.generation_control import GenerationControl

    closed = asyncio.Event()

    class Slow:
        async def stream(self, *args):
            try:
                await asyncio.Event().wait()
                yield None
            finally:
                closed.set()

    control = GenerationControl()
    iterator = events_with_keepalive(Slow(), [], "model", 8192, control)
    pending = asyncio.create_task(anext(iterator))
    await asyncio.sleep(0.01)
    control.cancelled.set()
    with pytest.raises(GenerationCancelled):
        await asyncio.wait_for(pending, 0.5)
    assert closed.is_set()


@pytest.mark.asyncio
async def test_embedding_requires_configuration_and_validates_dimensions(monkeypatch):
    settings = Settings(_env_file=None)
    with pytest.raises(EmbeddingError, match="not configured"):
        await embed_texts(["text"], settings)
    original = httpx.AsyncClient

    async def handler(request):
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1, 0]}]})

    monkeypatch.setattr(
        "app.services.embeddings.httpx.AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler)),
    )
    settings.embedding_api_key = "test"
    with pytest.raises(EmbeddingError, match="incompatible vectors"):
        await embed_texts(["text"], settings)
