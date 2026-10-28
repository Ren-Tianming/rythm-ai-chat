import math

import httpx

from app.core.config import Settings


class EmbeddingError(ValueError):
    pass


async def embed_texts(texts: list[str], settings: Settings) -> tuple[list[list[float]], int]:
    if not settings.embedding_api_key:
        raise EmbeddingError(
            "Embedding service is not configured; contact the administrator, then retry"
        )
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{settings.embedding_base_url.rstrip('/')}/embeddings",
                headers={"Authorization": f"Bearer {settings.embedding_api_key}"},
                json={
                    "model": settings.embedding_model,
                    "input": texts,
                    "dimensions": settings.embedding_dimensions,
                    "encoding_format": "float",
                },
            )
            response.raise_for_status()
            payload = response.json()
        data = sorted(payload["data"], key=lambda item: item["index"])
        vectors = [item["embedding"] for item in data]
        if len(vectors) != len(texts) or [item["index"] for item in data] != list(
            range(len(texts))
        ):
            raise ValueError()
        for vector in vectors:
            if (
                len(vector) != settings.embedding_dimensions
                or not all(math.isfinite(x) for x in vector)
                or not any(vector)
            ):
                raise ValueError()
        return vectors, int(payload.get("usage", {}).get("total_tokens", 0))
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise EmbeddingError(
            "Embedding service failed or returned incompatible vectors; retry later"
        ) from None
