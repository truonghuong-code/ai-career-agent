from collections.abc import Sequence

import pytest
from sqlalchemy import select

from app.db.models.document import Document, DocumentChunk
from app.db.repositories.documents import DocumentRepository
from app.integrations.storage.local import LocalDocumentStorage
from app.rag.chunking import DeterministicTextChunker
from app.rag.embeddings import (
    DeterministicEmbeddingProvider,
    EmbeddingProviderError,
)
from app.rag.parsers import DocumentParserRegistry
from app.services.document_service import (
    DocumentIngestionError,
    DocumentIngestionService,
    DocumentSearchService,
)


class FailingEmbeddingProvider:
    dimensions = 256

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        raise EmbeddingProviderError("Embedding failed for test")


async def test_ingestion_persists_document_chunks_and_source_metadata(
    db_session,
    storage_dir,
) -> None:
    service = DocumentIngestionService(
        repository=DocumentRepository(db_session),
        parsers=DocumentParserRegistry(),
        chunker=DeterministicTextChunker(
            chunk_size=24,
            chunk_overlap=4,
        ),
        embedding_provider=DeterministicEmbeddingProvider(dimensions=256),
        storage=LocalDocumentStorage(storage_dir),
    )

    content = b"Python PostgreSQL pgvector FastAPI career preparation"

    result = await service.ingest(
        owner_id="user-a",
        filename="career.txt",
        mime_type="text/plain",
        content=content,
    )

    stored = await DocumentRepository(db_session).get_document(
        result.document.id,
        "user-a",
    )

    assert stored is not None
    assert stored.processing_status == "completed"
    assert stored.error_message is None
    assert stored.extracted_text_length == len(content.decode("utf-8"))

    chunk_result = await db_session.execute(
        select(DocumentChunk).where(
            DocumentChunk.document_id == stored.id,
        )
    )
    stored_chunks = chunk_result.scalars().all()

    assert len(stored_chunks) == result.chunk_count
    assert result.chunk_count > 0
    assert (storage_dir / stored.storage_path).read_bytes() == content


async def test_semantic_retrieval_is_scoped_by_owner_and_document(
    db_session,
    storage_dir,
) -> None:
    provider = DeterministicEmbeddingProvider(dimensions=256)

    ingestion_service = DocumentIngestionService(
        repository=DocumentRepository(db_session),
        parsers=DocumentParserRegistry(),
        chunker=DeterministicTextChunker(
            chunk_size=200,
            chunk_overlap=20,
        ),
        embedding_provider=provider,
        storage=LocalDocumentStorage(storage_dir),
    )

    own_document = await ingestion_service.ingest(
        owner_id="user-a",
        filename="own.txt",
        mime_type="text/plain",
        content=b"Python FastAPI PostgreSQL pgvector application development",
    )

    await ingestion_service.ingest(
        owner_id="user-b",
        filename="other.txt",
        mime_type="text/plain",
        content=b"Python FastAPI PostgreSQL pgvector application development",
    )

    search_service = DocumentSearchService(
        DocumentRepository(db_session),
        provider,
    )

    results = await search_service.search(
        owner_id="user-a",
        query="FastAPI PostgreSQL",
        limit=5,
        document_ids=[own_document.document.id],
    )

    assert len(results) == 1
    assert results[0].chunk.document_id == own_document.document.id
    assert results[0].chunk.owner_id == "user-a"
    assert results[0].chunk.document.filename == "own.txt"


async def test_failed_ingestion_marks_document_as_failed(
    db_session,
    storage_dir,
) -> None:
    service = DocumentIngestionService(
        repository=DocumentRepository(db_session),
        parsers=DocumentParserRegistry(),
        chunker=DeterministicTextChunker(
            chunk_size=24,
            chunk_overlap=4,
        ),
        embedding_provider=FailingEmbeddingProvider(),
        storage=LocalDocumentStorage(storage_dir),
    )

    with pytest.raises(
        EmbeddingProviderError,
        match="Embedding failed for test",
    ):
        await service.ingest(
            owner_id="user-a",
            filename="career.txt",
            mime_type="text/plain",
            content=b"Python PostgreSQL pgvector FastAPI",
        )

    result = await db_session.execute(
        select(Document).where(
            Document.owner_id == "user-a",
            Document.filename == "career.txt",
        )
    )

    stored = result.scalar_one()

    assert stored.processing_status == "failed"
    assert stored.error_message == "Embedding failed for test"


async def test_failed_document_is_excluded_from_semantic_retrieval(
    db_session,
    storage_dir,
) -> None:
    provider = DeterministicEmbeddingProvider(dimensions=256)
    repository = DocumentRepository(db_session)

    ingestion_service = DocumentIngestionService(
        repository=repository,
        parsers=DocumentParserRegistry(),
        chunker=DeterministicTextChunker(
            chunk_size=200,
            chunk_overlap=20,
        ),
        embedding_provider=provider,
        storage=LocalDocumentStorage(storage_dir),
    )

    ingested = await ingestion_service.ingest(
        owner_id="user-a",
        filename="failed.txt",
        mime_type="text/plain",
        content=b"Python FastAPI PostgreSQL pgvector",
    )

    await repository.fail_document(
        ingested.document,
        "Forced failure for lifecycle test",
    )

    search_service = DocumentSearchService(
        repository,
        provider,
    )

    results = await search_service.search(
        owner_id="user-a",
        query="Python FastAPI PostgreSQL",
        limit=5,
        document_ids=[ingested.document.id],
    )

    assert results == []


class FailingCompletionDocumentRepository(DocumentRepository):
    async def complete_document(
        self,
        document,
        extracted_text_length: int,
    ) -> None:
        raise RuntimeError("Completion failed for test")


async def test_failed_ingestion_does_not_persist_chunks(
    db_session,
    storage_dir,
) -> None:
    repository = FailingCompletionDocumentRepository(db_session)

    service = DocumentIngestionService(
        repository=repository,
        parsers=DocumentParserRegistry(),
        chunker=DeterministicTextChunker(
            chunk_size=24,
            chunk_overlap=4,
        ),
        embedding_provider=DeterministicEmbeddingProvider(dimensions=256),
        storage=LocalDocumentStorage(storage_dir),
    )

    with pytest.raises(
        DocumentIngestionError,
        match="Document processing failed",
    ):
        await service.ingest(
            owner_id="user-a",
            filename="transaction-failure.txt",
            mime_type="text/plain",
            content=b"Python FastAPI PostgreSQL pgvector",
        )

    document_result = await db_session.execute(
        select(Document).where(
            Document.owner_id == "user-a",
            Document.filename == "transaction-failure.txt",
        )
    )
    stored_document = document_result.scalar_one()

    chunk_result = await db_session.execute(
        select(DocumentChunk).where(
            DocumentChunk.document_id == stored_document.id,
        )
    )
    stored_chunks = chunk_result.scalars().all()

    assert stored_document.processing_status == "failed"
    assert stored_chunks == []


async def test_tn_004_ingestion_chunks_normalized_text_and_keeps_raw_extracted_length(
    db_session,
    storage_dir,
) -> None:
    content = b"\r\nFirst paragraph\r\n\r\n\r\nSecond paragraph\r\n"
    service = DocumentIngestionService(
        repository=DocumentRepository(db_session),
        parsers=DocumentParserRegistry(),
        chunker=DeterministicTextChunker(chunk_size=200, chunk_overlap=20),
        embedding_provider=DeterministicEmbeddingProvider(dimensions=256),
        storage=LocalDocumentStorage(storage_dir),
    )

    ingested = await service.ingest(
        owner_id="user-a",
        filename="normalized.txt",
        mime_type="text/plain",
        content=content,
    )
    chunk_result = await db_session.execute(
        select(DocumentChunk).where(DocumentChunk.document_id == ingested.document.id)
    )

    assert [chunk.text for chunk in chunk_result.scalars().all()] == [
        "First paragraph Second paragraph"
    ]
    assert ingested.document.extracted_text_length == len(content.decode("utf-8"))


async def test_tn_005_whitespace_only_content_completes_without_chunks(
    db_session, storage_dir
) -> None:
    content = b" \r\n\t \r\n"
    service = DocumentIngestionService(
        repository=DocumentRepository(db_session),
        parsers=DocumentParserRegistry(),
        chunker=DeterministicTextChunker(chunk_size=200, chunk_overlap=20),
        embedding_provider=DeterministicEmbeddingProvider(dimensions=256),
        storage=LocalDocumentStorage(storage_dir),
    )

    ingested = await service.ingest(
        owner_id="user-a",
        filename="empty.txt",
        mime_type="text/plain",
        content=content,
    )
    chunk_result = await db_session.execute(
        select(DocumentChunk).where(DocumentChunk.document_id == ingested.document.id)
    )

    assert ingested.document.processing_status == "completed"
    assert ingested.document.extracted_text_length == len(content.decode("utf-8"))
    assert chunk_result.scalars().all() == []
