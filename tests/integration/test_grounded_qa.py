from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import update

from app.api.v1.endpoints.qa import get_qa_service
from app.db.models.document import Document, DocumentStatus
from app.db.repositories.documents import DocumentRepository
from app.integrations.llm.provider import (
    FakeLLMProvider,
    LLMProviderError,
    LLMResponse,
    LLMTimeoutError,
)
from app.main import create_app
from app.rag.embeddings import DeterministicEmbeddingProvider
from app.schemas.qa import QAResponse
from app.services.document_service import DocumentSearchService
from app.services.qa_service import GroundedQAService
from tests.integration.test_retrieval_filtering import _create_ingestion_service


@pytest.fixture
async def pipeline(db_session, storage_dir):
    embedding = DeterministicEmbeddingProvider(256)
    ingestion = _create_ingestion_service(db_session, storage_dir, embedding)
    owned = await ingestion.ingest(
        owner_id="owner",
        filename="python.txt",
        mime_type="text/plain",
        content=b"Python experience is three years.",
    )
    foreign = await ingestion.ingest(
        owner_id="other",
        filename="private.txt",
        mime_type="text/plain",
        content=b"Private salary information.",
    )
    search = DocumentSearchService(DocumentRepository(db_session), embedding)
    provider = FakeLLMProvider(LLMResponse("Three years [Source 1]", (1,), False))
    service = GroundedQAService(search, provider)
    app = create_app()
    app.dependency_overrides[get_qa_service] = lambda: service
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, service, owned.document.id, foreign.document.id


async def test_ingestion_to_grounded_api_is_deterministic(pipeline):
    client, service, owned, foreign = pipeline
    payload = {"question": "Python experience", "document_ids": [str(owned), str(foreign)]}
    first = await client.post("/api/v1/qa", json=payload, headers={"X-Internal-User-ID": "owner"})
    second = await client.post("/api/v1/qa", json=payload, headers={"X-Internal-User-ID": "owner"})
    assert first.status_code == 200
    assert first.json() == second.json()
    parsed = QAResponse.model_validate(first.json())
    assert parsed.status == "answered"
    assert [s.document_id for s in parsed.sources] == [owned]
    results = await service.search_service.search(
        owner_id="owner", query="Python experience", limit=5, document_ids=[owned]
    )
    assert parsed.sources[0].chunk_id == results[0].chunk.id
    assert parsed.sources[0].chunk_index == results[0].chunk.chunk_index
    assert parsed.sources[0].number == 1


@pytest.mark.parametrize("selection", ["foreign", "empty", "unknown_owner"])
async def test_ownership_and_no_context(pipeline, selection):
    client, service, owned, foreign = pipeline
    service.llm_provider.generate = AsyncMock(side_effect=AssertionError("LLM must not run"))
    ids = [str(foreign)] if selection == "foreign" else []
    body = {"question": "Python", "document_ids": ids}
    owner = "owner"
    if selection == "unknown_owner":
        owner = "nobody"
        body.pop("document_ids")
    response = await client.post("/api/v1/qa", json=body, headers={"X-Internal-User-ID": owner})
    assert response.status_code == 200
    assert response.json()["status"] == "no_context"
    assert response.json()["sources"] == []
    service.llm_provider.generate.assert_not_awaited()


async def test_incomplete_documents_are_excluded(pipeline, db_session):
    client, service, owned, foreign = pipeline
    await db_session.execute(
        update(Document)
        .where(Document.id == owned)
        .values(processing_status=DocumentStatus.FAILED.value)
    )
    await db_session.commit()
    response = await client.post(
        "/api/v1/qa", json={"question": "Python"}, headers={"X-Internal-User-ID": "owner"}
    )
    assert response.json()["status"] == "no_context"


async def test_insufficient_evidence_with_real_retrieval(pipeline):
    client, service, owned, foreign = pipeline
    service.llm_provider = FakeLLMProvider()
    response = await client.post(
        "/api/v1/qa", json={"question": "Unknown fact"}, headers={"X-Internal-User-ID": "owner"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "insufficient_evidence"
    assert response.json()["sources"] == []


@pytest.mark.parametrize("error,status", [(LLMProviderError, 502), (LLMTimeoutError, 504)])
async def test_provider_errors_after_real_retrieval(pipeline, error, status):
    client, service, owned, foreign = pipeline
    service.llm_provider.generate = AsyncMock(side_effect=error("secret"))
    response = await client.post(
        "/api/v1/qa", json={"question": "Python"}, headers={"X-Internal-User-ID": "owner"}
    )
    assert response.status_code == status
    assert "secret" not in response.text
