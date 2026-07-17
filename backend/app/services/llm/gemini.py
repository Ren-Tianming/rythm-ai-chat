import json
from collections.abc import AsyncIterator

import httpx

from app.services.llm.base import BaseLLMProvider, LLMMessage, ProviderError, ProviderEvent


class GeminiProvider(BaseLLMProvider):
    def __init__(self, *, api_key: str, base_url: str, timeout: float):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def stream(
        self, messages: list[LLMMessage], model_id: str, max_tokens: int
    ) -> AsyncIterator[ProviderEvent]:
        if not self.api_key:
            raise ProviderError("provider_not_configured", "Gemini API key is missing", 503)
        system_parts = [m.content for m in messages if m.role == "system"]
        contents = [
            {
                "role": "model" if message.role == "assistant" else "user",
                "parts": [{"text": message.content}],
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
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST", url, params={"alt": "sse", "key": self.api_key}, json=payload
                ) as response:
                    if response.status_code >= 400:
                        body = (await response.aread()).decode("utf-8", errors="replace")[:500]
                        code = "provider_rate_limited" if response.status_code == 429 else "provider_error"
                        raise ProviderError(code, f"Gemini returned {response.status_code}: {body}")
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
            raise ProviderError("provider_timeout", "Gemini timed out", 504) from exc
        except httpx.HTTPError as exc:
            raise ProviderError("provider_unavailable", "Gemini is unavailable") from exc
