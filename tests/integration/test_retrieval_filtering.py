from sqlalchemy import update

from app.db.models.document import Document, DocumentChunk, DocumentStatus
from app.db.repositories.documents import DocumentRepository
from app.integrations.storage.local import LocalDocumentStorage
from app.rag.chunking import DeterministicTextChunker
from app.rag.embeddings import DeterministicEmbeddingProvider
from app.rag.parsers import DocumentParserRegistry
from app.services.document_service import DocumentIngestionService, DocumentSearchService


def _create_ingestion_service(
    db_session, storage_dir, provider: DeterministicEmbeddingProvider
) -> DocumentIngestionService:
    return DocumentIngestionService(
        repository=DocumentRepository(db_session),
        parsers=DocumentParserRegistry(),
        chunker=DeterministicTextChunker(chunk_size=200, chunk_overlap=20),
        embedding_provider=provider,
        storage=LocalDocumentStorage(storage_dir),
    )


def _create_search_service(
    db_session, provider: DeterministicEmbeddingProvider
) -> DocumentSearchService:
    return DocumentSearchService(DocumentRepository(db_session), provider)


async def test_rf_001_search_scopes_both_chunk_and_document_owners(db_session, storage_dir) -> None:
    provider = DeterministicEmbeddingProvider(dimensions=256)
    ingestion_service = _create_ingestion_service(db_session, storage_dir, provider)

    owner_a_document = await ingestion_service.ingest(
        owner_id="user-a",
        filename="owner-a.txt",
        mime_type="text/plain",
        content=b"FastAPI PostgreSQL document retrieval",
    )
    owner_b_document = await ingestion_service.ingest(
        owner_id="user-b",
        filename="owner-b.txt",
        mime_type="text/plain",
        content=b"FastAPI PostgreSQL document retrieval",
    )
    await db_session.execute(
        update(DocumentChunk)
        .where(DocumentChunk.document_id == owner_a_document.document.id)
        .values(owner_id="user-b")
    )
    await db_session.execute(
        update(DocumentChunk)
        .where(DocumentChunk.document_id == owner_b_document.document.id)
        .values(owner_id="user-a")
    )
    await db_session.commit()

    results = await _create_search_service(db_session, provider).search(
        owner_id="user-a",
        query="FastAPI PostgreSQL",
        limit=5,
        document_ids=None,
    )

    assert results == []


async def test_rf_002_search_returns_only_completed_documents(db_session, storage_dir) -> None:
    provider = DeterministicEmbeddingProvider(dimensions=256)
    ingestion_service = _create_ingestion_service(db_session, storage_dir, provider)

    completed = await ingestion_service.ingest(
        owner_id="user-a",
        filename="completed.txt",
        mime_type="text/plain",
        content=b"FastAPI PostgreSQL completed document",
    )
    processing = await ingestion_service.ingest(
        owner_id="user-a",
        filename="processing.txt",
        mime_type="text/plain",
        content=b"FastAPI PostgreSQL processing document",
    )
    failed = await ingestion_service.ingest(
        owner_id="user-a",
        filename="failed.txt",
        mime_type="text/plain",
        content=b"FastAPI PostgreSQL failed document",
    )
    await db_session.execute(
        update(Document)
        .where(Document.id == processing.document.id)
        .values(processing_status=DocumentStatus.PROCESSING.value)
    )
    await db_session.execute(
        update(Document)
        .where(Document.id == failed.document.id)
        .values(processing_status=DocumentStatus.FAILED.value)
    )
    await db_session.commit()

    results = await _create_search_service(db_session, provider).search(
        owner_id="user-a",
        query="FastAPI PostgreSQL document",
        limit=5,
        document_ids=None,
    )

    assert {result.chunk.document_id for result in results} == {completed.document.id}


async def test_rf_003_document_id_filter_stays_owner_scoped(db_session, storage_dir) -> None:
    provider = DeterministicEmbeddingProvider(dimensions=256)
    ingestion_service = _create_ingestion_service(db_session, storage_dir, provider)

    selected = await ingestion_service.ingest(
        owner_id="user-a",
        filename="selected.txt",
        mime_type="text/plain",
        content=b"FastAPI PostgreSQL selected document",
    )
    await ingestion_service.ingest(
        owner_id="user-a",
        filename="unselected.txt",
        mime_type="text/plain",
        content=b"FastAPI PostgreSQL unselected document",
    )
    other_owner = await ingestion_service.ingest(
        owner_id="user-b",
        filename="other-owner.txt",
        mime_type="text/plain",
        content=b"FastAPI PostgreSQL other owner document",
    )

    results = await _create_search_service(db_session, provider).search(
        owner_id="user-a",
        query="FastAPI PostgreSQL document",
        limit=5,
        document_ids=[selected.document.id, other_owner.document.id],
    )

    assert {result.chunk.document_id for result in results} == {selected.document.id}


async def test_rf_004_empty_document_id_filter_returns_no_results(db_session, storage_dir) -> None:
    provider = DeterministicEmbeddingProvider(dimensions=256)
    ingestion_service = _create_ingestion_service(db_session, storage_dir, provider)
    await ingestion_service.ingest(
        owner_id="user-a",
        filename="owned.txt",
        mime_type="text/plain",
        content=b"FastAPI PostgreSQL document",
    )

    results = await _create_search_service(db_session, provider).search(
        owner_id="user-a",
        query="FastAPI PostgreSQL",
        limit=5,
        document_ids=[],
    )

    assert results == []


async def test_rf_005_search_respects_result_limit(db_session, storage_dir) -> None:
    provider = DeterministicEmbeddingProvider(dimensions=256)
    ingestion_service = _create_ingestion_service(db_session, storage_dir, provider)
    for index in range(3):
        await ingestion_service.ingest(
            owner_id="user-a",
            filename=f"document-{index}.txt",
            mime_type="text/plain",
            content=b"FastAPI PostgreSQL document retrieval",
        )

    results = await _create_search_service(db_session, provider).search(
        owner_id="user-a",
        query="FastAPI PostgreSQL",
        limit=2,
        document_ids=None,
    )

    assert len(results) == 2
