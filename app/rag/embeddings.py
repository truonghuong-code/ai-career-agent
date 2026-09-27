import hashlib
import math
import re
from collections.abc import Sequence
from typing import Protocol

from openai import AsyncOpenAI

from app.core.config import Settings


class EmbeddingProviderError(RuntimeError):
    """Raised when an embedding provider cannot generate embeddings."""


class EmbeddingProvider(Protocol):
    dimensions: int

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class DeterministicEmbeddingProvider:
    """A dependency-free hashed token embedding for local development and tests.

    It is deterministic and useful for exercising the retrieval pipeline. Production
    deployments should configure a semantic embedding provider such as OpenAI.
    """

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in re.findall(r"\w+", text.lower(), flags=re.UNICODE):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector


class OpenAIEmbeddingProvider:
    def __init__(self, api_key: str, model: str, dimensions: int) -> None:
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.dimensions = dimensions

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        try:
            response = await self.client.embeddings.create(
                model=self.model, input=list(texts), dimensions=self.dimensions
            )
        except Exception as exc:
            raise EmbeddingProviderError("OpenAI embedding request failed") from exc
        return [item.embedding for item in response.data]


def create_embedding_provider(settings: Settings) -> EmbeddingProvider:
    if settings.embedding_dimensions != 256:
        raise ValueError("EMBEDDING_DIMENSIONS must be 256 to match the current database schema")
    if settings.embedding_provider == "deterministic":
        return DeterministicEmbeddingProvider(settings.embedding_dimensions)
    if settings.embedding_provider == "openai":
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when EMBEDDING_PROVIDER=openai")
        return OpenAIEmbeddingProvider(
            api_key=settings.openai_api_key,
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )
    raise ValueError(f"Unsupported embedding provider: {settings.embedding_provider}")
