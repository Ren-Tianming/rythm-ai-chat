import httpx
import pytest

from app.services.llm.base import LLMMessage, OpenAICompatibleProvider, ProviderError


@pytest.mark.asyncio
async def test_provider_error_is_normalized_without_upstream_body() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="secret upstream diagnostic")

    provider = OpenAICompatibleProvider(
        api_key="test-key",
        base_url="https://provider.example",
        timeout=10,
        provider="Test",
    )
    await provider.client.aclose()
    provider.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    with pytest.raises(ProviderError) as raised:
        _ = [
            event
            async for event in provider.stream(
                [LLMMessage(role="user", content="hello")],
                "test-model",
                32,
            )
        ]
    assert raised.value.code == "MODEL_RATE_LIMITED"
    assert raised.value.retryable
    assert "secret upstream diagnostic" not in str(raised.value)
    await provider.aclose()
