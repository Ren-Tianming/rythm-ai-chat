from app.core.config import Settings
from app.services.llm.base import BaseLLMProvider, OpenAICompatibleProvider
from app.services.llm.gemini import GeminiProvider


class ProviderRegistry:
    def __init__(self, settings: Settings):
        timeout = settings.provider_timeout_seconds
        self.providers: dict[str, BaseLLMProvider] = {
            "deepseek": OpenAICompatibleProvider(
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
                timeout=timeout,
                provider="DeepSeek",
            ),
            "groq": OpenAICompatibleProvider(
                api_key=settings.groq_api_key,
                base_url=settings.groq_base_url,
                timeout=timeout,
                provider="Groq",
            ),
            "gemini": GeminiProvider(
                api_key=settings.gemini_api_key,
                base_url=settings.gemini_base_url,
                timeout=timeout,
            ),
        }

    def get(self, provider: str) -> BaseLLMProvider:
        try:
            return self.providers[provider]
        except KeyError as exc:
            raise ValueError(f"Unsupported provider: {provider}") from exc


def estimate_cost_microusd(provider: str, model_id: str, input_tokens: int, output_tokens: int) -> int:
    prices = {
        ("deepseek", "deepseek-v4-flash"): (0.14, 0.28),
        ("gemini", "gemini-3.1-flash-lite"): (0.25, 1.50),
        ("groq", "openai/gpt-oss-20b"): (0.075, 0.30),
        ("groq", "llama-3.1-8b-instant"): (0.05, 0.08),
    }
    input_price, output_price = prices.get((provider, model_id), (0.0, 0.0))
    return round(input_tokens * input_price + output_tokens * output_price)
