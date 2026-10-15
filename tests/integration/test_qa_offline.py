"""HTTP + real orchestration/builders/embedding, replacing only persistence and LLM.

These tests run without PostgreSQL; database ownership enforcement is covered by
 test_grounded_qa and existing retrieval filtering tests, not by this stub.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from app.api.v1.endpoints.qa import get_qa_service
from app.db.models.document import DocumentChunk
from app.db.repositories.documents import RetrievedChunk
from app.integrations.llm.provider import FakeLLMProvider, LLMResponse
from app.main import create_app
from app.rag.embeddings import DeterministicEmbeddingProvider
from app.schemas.qa import QAResponse
from app.services.document_service import DocumentSearchService
from app.services.qa_service import GroundedQAService


@pytest.mark.parametrize(
    "scenario,status",
    [
        ("success", 200),
        ("empty", 200),
        ("insufficient", 200),
        ("invented_citation", 502),
        ("provider_failure", 502),
        ("timeout", 504),
        ("retrieval_failure", 503),
        ("invalid_input", 422),
    ],
)
async def test_offline_http_pipeline(scenario, status, caplog):
    chunk = DocumentChunk(
        id=uuid4(),
        document_id=uuid4(),
        chunk_index=2,
        text="Python experience is three years.",
        owner_id="owner",
    )
    repository = SimpleNamespace(search=AsyncMock(return_value=[RetrievedChunk(chunk, 0.9)]))
    provider = FakeLLMProvider(LLMResponse("Three years [Source 1]", (1,), False))
    if scenario == "empty":
        repository.search.return_value = []
        provider.generate = AsyncMock(side_effect=AssertionError("Must not generate"))
    elif scenario == "insufficient":
        provider = FakeLLMProvider()
    elif scenario == "invented_citation":
        provider = FakeLLMProvider(LLMResponse("Three years [Source 99]", (99,), False))
    elif scenario == "provider_failure":
        provider.generate = AsyncMock(side_effect=RuntimeError("secret-provider-error"))
    elif scenario == "timeout":

        async def delayed(messages):
            await asyncio.sleep(10)

        provider.generate = delayed
    elif scenario == "retrieval_failure":
        repository.search.side_effect = RuntimeError("secret-db-error")
    service = GroundedQAService(
        DocumentSearchService(repository, DeterministicEmbeddingProvider(256)),
        provider,
        timeout_seconds=0.01,
    )
    app = create_app()
    app.dependency_overrides[get_qa_service] = lambda: service
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/qa",
            json={"question": "  " if scenario == "invalid_input" else "Python experience"},
            headers={"X-Internal-User-ID": "owner", "X-Request-ID": "offline-qa"},
        )
    assert response.status_code == status
    assert response.headers["X-Request-ID"] == "offline-qa"
    assert "secret" not in response.text
    assert "secret" not in caplog.text
    if scenario == "success":
        result = QAResponse.model_validate(response.json())
        assert result.status == "answered"
        assert result.sources[0].document_id == chunk.document_id
        assert result.sources[0].chunk_id == chunk.id
        assert result.sources[0].chunk_index == 2
        assert result.sources[0].number == 1
        assert repository.search.call_args.kwargs["owner_id"] == "owner"
        assert len(repository.search.call_args.kwargs["query_embedding"]) == 256
    elif scenario in ("empty", "insufficient"):
        assert response.json()["sources"] == []
        assert response.json()["status"] == (
            "no_context" if scenario == "empty" else "insufficient_evidence"
        )
    if scenario == "empty":
        provider.generate.assert_not_awaited()
    if scenario == "invalid_input":
        repository.search.assert_not_awaited()
