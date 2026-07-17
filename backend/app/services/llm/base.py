import json
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class LLMMessage:
    role: str
    content: str


@dataclass
class ProviderEvent:
    text: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish_reason: str | None = None
    request_id: str | None = None


class ProviderError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int = 502):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class BaseLLMProvider:
    async def stream(
        self, messages: list[LLMMessage], model_id: str, max_tokens: int
    ) -> AsyncIterator[ProviderEvent]:
        raise NotImplementedError


class OpenAICompatibleProvider(BaseLLMProvider):
    def __init__(self, *, api_key: str, base_url: str, timeout: float, provider: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.provider = provider

    async def stream(
        self, messages: list[LLMMessage], model_id: str, max_tokens: int
    ) -> AsyncIterator[ProviderEvent]:
        if not self.api_key:
            raise ProviderError("provider_not_configured", f"{self.provider} API key is missing", 503)
        payload = {
            "model": model_id,
            "messages": [{"role": message.role, "content": message.content} for message in messages],
            "max_tokens": max_tokens,
            "temperature": 0.7,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST", f"{self.base_url}/chat/completions", json=payload, headers=headers
                ) as response:
                    if response.status_code >= 400:
                        body = (await response.aread()).decode("utf-8", errors="replace")[:500]
                        code = "provider_rate_limited" if response.status_code == 429 else "provider_error"
                        raise ProviderError(code, f"{self.provider} returned {response.status_code}: {body}")
                    request_id = response.headers.get("x-request-id")
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if not data or data == "[DONE]":
                            continue
                        try:
                            item = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        choice = (item.get("choices") or [{}])[0]
                        delta = choice.get("delta") or {}
                        usage = item.get("usage") or {}
                        yield ProviderEvent(
                            text=delta.get("content") or "",
                            input_tokens=usage.get("prompt_tokens"),
                            output_tokens=usage.get("completion_tokens"),
                            finish_reason=choice.get("finish_reason"),
                            request_id=request_id or item.get("id"),
                        )
        except httpx.TimeoutException as exc:
            raise ProviderError("provider_timeout", f"{self.provider} timed out", 504) from exc
        except httpx.HTTPError as exc:
            raise ProviderError("provider_unavailable", f"{self.provider} is unavailable") from exc
