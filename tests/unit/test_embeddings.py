import pytest

from app.core.config import Settings
from app.rag.embeddings import DeterministicEmbeddingProvider, create_embedding_provider


@pytest.mark.asyncio
async def test_deterministic_embedding_is_stable_and_normalized() -> None:
    provider = DeterministicEmbeddingProvider(dimensions=8)

    embeddings = await provider.embed(["Python PostgreSQL", "Python PostgreSQL"])

    assert embeddings[0] == embeddings[1]
    assert len(embeddings[0]) == 8
    assert sum(value * value for value in embeddings[0]) == pytest.approx(1.0)


def test_embedding_provider_factory_returns_configured_provider() -> None:
    settings = Settings(
        _env_file=None, embedding_provider="deterministic", embedding_dimensions=256
    )

    provider = create_embedding_provider(settings)

    assert isinstance(provider, DeterministicEmbeddingProvider)
    assert provider.dimensions == 256
