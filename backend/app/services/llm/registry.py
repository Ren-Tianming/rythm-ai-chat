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

    async def aclose(self) -> None:
        for provider in self.providers.values():
            await provider.aclose()


def configured_provider_names(settings: Settings) -> set[str]:
    configured: set[str] = set()
    if settings.deepseek_api_key and settings.deepseek_model:
        configured.add("deepseek")
    if settings.gemini_api_key and settings.gemini_model:
        configured.add("gemini")
    if settings.groq_api_key and settings.groq_model:
        configured.add("groq")
    return configured


def configured_model_id(provider: str, database_model_id: str, settings: Settings) -> str:
    overrides = {
        "deepseek": settings.deepseek_model,
        "gemini": settings.gemini_model,
        "groq": settings.groq_model,
    }
    return overrides.get(provider) or database_model_id


def estimate_cost_microusd(
    provider: str,
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    input_price: float | None = None,
    output_price: float | None = None,
) -> int:
    prices = {
        ("deepseek", "deepseek-v4-flash"): (0.14, 0.28),
        ("gemini", "gemini-3.1-flash-lite"): (0.25, 1.50),
        ("groq", "openai/gpt-oss-20b"): (0.075, 0.30),
        ("groq", "llama-3.1-8b-instant"): (0.05, 0.08),
    }
    if input_price is None or output_price is None:
        input_price, output_price = prices.get((provider, model_id), (0.0, 0.0))
    return round(input_tokens * input_price + output_tokens * output_price)
