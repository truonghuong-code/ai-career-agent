from app.db.repositories.documents import DocumentRepository
from app.integrations.storage.local import LocalDocumentStorage
from app.rag.chunking import DeterministicTextChunker
from app.rag.embeddings import DeterministicEmbeddingProvider
from app.rag.parsers import DocumentParserRegistry
from app.services.document_service import DocumentIngestionService, DocumentSearchService


def _create_ingestion_service(
    db_session,
    storage_dir,
    provider: DeterministicEmbeddingProvider,
    *,
    chunk_size: int = 200,
) -> DocumentIngestionService:
    return DocumentIngestionService(
        repository=DocumentRepository(db_session),
        parsers=DocumentParserRegistry(),
        chunker=DeterministicTextChunker(chunk_size=chunk_size, chunk_overlap=10),
        embedding_provider=provider,
        storage=LocalDocumentStorage(storage_dir),
    )


def _create_search_service(
    db_session, provider: DeterministicEmbeddingProvider
) -> DocumentSearchService:
    return DocumentSearchService(DocumentRepository(db_session), provider)


async def test_rq_001_repeated_deterministic_search_has_stable_order_and_scores(
    db_session, storage_dir
) -> None:
    provider = DeterministicEmbeddingProvider(dimensions=256)
    ingestion_service = _create_ingestion_service(db_session, storage_dir, provider)
    exact = await ingestion_service.ingest(
        owner_id="user-a",
        filename="exact.txt",
        mime_type="text/plain",
        content=b"FastAPI PostgreSQL vector retrieval",
    )
    related = await ingestion_service.ingest(
        owner_id="user-a",
        filename="related.txt",
        mime_type="text/plain",
        content=b"FastAPI document retrieval",
    )
    search_service = _create_search_service(db_session, provider)
    search_arguments = {
        "owner_id": "user-a",
        "query": "FastAPI PostgreSQL vector retrieval",
        "limit": 5,
        "document_ids": [exact.document.id, related.document.id],
    }

    first = await search_service.search(**search_arguments)
    second = await search_service.search(**search_arguments)

    assert [(match.chunk.id, match.score) for match in first] == [
        (match.chunk.id, match.score) for match in second
    ]
    assert [match.chunk.document_id for match in first] == [
        exact.document.id,
        related.document.id,
    ]


async def test_rq_002_normalized_and_chunked_text_remains_retrievable(
    db_session, storage_dir
) -> None:
    provider = DeterministicEmbeddingProvider(dimensions=256)
    ingestion_service = _create_ingestion_service(db_session, storage_dir, provider, chunk_size=45)
    ingested = await ingestion_service.ingest(
        owner_id="user-a",
        filename="normalized.txt",
        mime_type="text/plain",
        content=(b"Heading\r\n\r\n\r\nFastAPI PostgreSQL retrieval guidance\r\n\r\n\r\nConclusion"),
    )

    matches = await _create_search_service(db_session, provider).search(
        owner_id="user-a",
        query="FastAPI PostgreSQL retrieval",
        limit=5,
        document_ids=[ingested.document.id],
    )

    assert matches[0].chunk.text == "Heading\n\nFastAPI PostgreSQL retrieval"
    assert "\r" not in matches[0].chunk.text
    assert "\n\n" in matches[0].chunk.text


async def test_rq_003_search_without_eligible_documents_returns_empty_results(
    db_session, storage_dir
) -> None:
    provider = DeterministicEmbeddingProvider(dimensions=256)

    results = await _create_search_service(db_session, provider).search(
        owner_id="owner-without-documents",
        query="FastAPI PostgreSQL",
        limit=5,
        document_ids=None,
    )

    assert results == []
