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
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 503,
        *,
        retryable: bool = False,
    ):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.retryable = retryable


class BaseLLMProvider:
    async def stream(
        self, messages: list[LLMMessage], model_id: str, max_tokens: int
    ) -> AsyncIterator[ProviderEvent]:
        raise NotImplementedError

    async def aclose(self) -> None:
        return None


class OpenAICompatibleProvider(BaseLLMProvider):
    def __init__(self, *, api_key: str, base_url: str, timeout: float, provider: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.provider = provider
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=min(10.0, timeout)),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

    async def stream(
        self, messages: list[LLMMessage], model_id: str, max_tokens: int
    ) -> AsyncIterator[ProviderEvent]:
        if not self.api_key:
            raise ProviderError("MODEL_NOT_CONFIGURED", "The selected model is not configured")
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
            async with self.client.stream(
                    "POST", f"{self.base_url}/chat/completions", json=payload, headers=headers
                ) as response:
                    if response.status_code >= 400:
                        await response.aread()
                        if response.status_code == 429:
                            raise ProviderError(
                                "MODEL_RATE_LIMITED",
                                "The model is temporarily rate limited",
                                retryable=True,
                            )
                        if response.status_code in {401, 403}:
                            raise ProviderError(
                                "MODEL_AUTH_FAILED", "The model is temporarily unavailable"
                            )
                        if response.status_code == 404:
                            raise ProviderError(
                                "MODEL_NOT_FOUND", "The selected model is unavailable"
                            )
                        raise ProviderError(
                            "MODEL_UPSTREAM_ERROR",
                            "The model service returned an error",
                            retryable=response.status_code >= 500,
                        )
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
            raise ProviderError(
                "MODEL_TIMEOUT", "The model response timed out", 504, retryable=True
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                "MODEL_UPSTREAM_ERROR", "The model service is unavailable", retryable=True
            ) from exc

    async def aclose(self) -> None:
        await self.client.aclose()
