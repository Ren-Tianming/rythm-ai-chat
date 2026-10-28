import json
from collections.abc import AsyncIterator

import httpx

from app.services.llm.base import BaseLLMProvider, LLMMessage, ProviderError, ProviderEvent


class GeminiProvider(BaseLLMProvider):
    def __init__(self, *, api_key: str, base_url: str, timeout: float):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=min(10.0, timeout)),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

    async def stream(
        self, messages: list[LLMMessage], model_id: str, max_tokens: int
    ) -> AsyncIterator[ProviderEvent]:
        if not self.api_key:
            raise ProviderError("MODEL_NOT_CONFIGURED", "The selected model is not configured")
        system_parts = [m.content for m in messages if m.role == "system"]
        contents = [
            {
                "role": "model" if message.role == "assistant" else "user",
                "parts": [{"text": message.content}]
                + [
                    {"inlineData": {"mimeType": image["mime_type"], "data": image["data"]}}
                    for image in message.images
                ],
            }
            for message in messages
            if message.role != "system"
        ]
        payload: dict[str, object] = {
            "contents": contents,
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.7},
        }
        if system_parts:
            payload["systemInstruction"] = {"parts": [{"text": "\n".join(system_parts)}]}
        url = f"{self.base_url}/models/{model_id}:streamGenerateContent"
        try:
            async with self.client.stream(
                "POST", url, params={"alt": "sse", "key": self.api_key}, json=payload
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
                        raise ProviderError("MODEL_NOT_FOUND", "The selected model is unavailable")
                    raise ProviderError(
                        "MODEL_UPSTREAM_ERROR",
                        "The model service returned an error",
                        retryable=response.status_code >= 500,
                    )
                request_id = response.headers.get("x-request-id")
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    try:
                        item = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
                    candidates = item.get("candidates") or []
                    candidate = candidates[0] if candidates else {}
                    parts = (candidate.get("content") or {}).get("parts") or []
                    text = "".join(part.get("text", "") for part in parts)
                    usage = item.get("usageMetadata") or {}
                    yield ProviderEvent(
                        text=text,
                        input_tokens=usage.get("promptTokenCount"),
                        output_tokens=usage.get("candidatesTokenCount"),
                        finish_reason=candidate.get("finishReason"),
                        request_id=request_id,
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
