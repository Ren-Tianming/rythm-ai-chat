from functools import lru_cache
import tiktoken

from app.core.config import Settings
from app.db.models import ModelProfile


@lru_cache
def tokenizer():
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(tokenizer().encode(text, disallowed_special=()))


def output_budget(model: ModelProfile, settings: Settings, messages) -> int:
    config = model.config_json or {}
    # UTF-8 bytes are a conservative upper bound for byte-BPE input models.
    image_tokens = int(config.get("vision_tokens_per_image", 4096))
    input_budget = sum(len(m.content.encode("utf-8")) + 16 for m in messages) + image_tokens * sum(
        len(m.images) for m in messages
    )
    remaining = int(config.get("context_window_tokens", 32768)) - input_budget - 256
    limits = [model.max_output_tokens, model.default_output_tokens, remaining]
    if settings.max_output_tokens is not None:
        limits.append(settings.max_output_tokens)
    cost_cap = config.get("max_generation_cost_usd")
    if cost_cap is not None and model.output_price_per_million is None:
        raise ValueError("A monetary generation budget requires model pricing to be configured")
    if cost_cap is not None and model.output_price_per_million:
        available = float(cost_cap) * 1_000_000 - input_budget * float(
            model.input_price_per_million or 0
        )
        limits.append(int(available / float(model.output_price_per_million)))
    result = min(limits)
    if result < 1:
        raise ValueError(
            "Model context or cost budget is exhausted; start a new conversation or select fewer documents"
        )
    return result


def chunk_pages(pages: list[dict], settings: Settings) -> list[dict]:
    chunks = []
    encoding = tokenizer()
    for page in pages:
        # Keep page boundaries. Prefer paragraph/title boundaries within token-sized windows.
        paragraphs = page["text"].strip().split("\n\n")
        text = "\n\n".join(p.strip() for p in paragraphs if p.strip())
        tokens = encoding.encode(text, disallowed_special=())
        start = 0
        while start < len(tokens):
            end = min(start + settings.chunk_tokens, len(tokens))
            part = encoding.decode(tokens[start:end])
            if end < len(tokens):
                boundary = part.rfind("\n\n")
                if boundary > len(part) * 0.65:
                    consumed = len(encoding.encode(part[:boundary], disallowed_special=()))
                    end = start + consumed
                    part = encoding.decode(tokens[start:end])
            # BPE splits can bisect a Unicode character; align to full UTF-8 boundaries.
            while part.endswith("\ufffd") and end < len(tokens):
                end += 1
                part = encoding.decode(tokens[start:end])
            if part.strip():
                chunks.append(
                    {"page_number": page["page"], "content": part, "token_count": end - start}
                )
            if end == len(tokens):
                break
            start = max(start + 1, end - settings.chunk_overlap_tokens)
            while start < end and encoding.decode(tokens[start:end]).startswith("\ufffd"):
                start += 1
    return chunks
