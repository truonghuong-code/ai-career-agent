from app.db.repositories.documents import DocumentRepository
from app.integrations.storage.local import LocalDocumentStorage
from app.rag.chunking import DeterministicTextChunker
from app.rag.embeddings import DeterministicEmbeddingProvider
from app.rag.parsers import DocumentParserRegistry
from app.services.document_service import DocumentIngestionService, DocumentSearchService


async def test_ingestion_persists_document_chunks_and_source_metadata(
    db_session, storage_dir
) -> None:
    service = DocumentIngestionService(
        repository=DocumentRepository(db_session),
        parsers=DocumentParserRegistry(),
        chunker=DeterministicTextChunker(chunk_size=24, chunk_overlap=4),
        embedding_provider=DeterministicEmbeddingProvider(dimensions=256),
        storage=LocalDocumentStorage(storage_dir),
    )

    result = await service.ingest(
        owner_id="user-a",
        filename="career.txt",
        mime_type="text/plain",
        content=b"Python PostgreSQL pgvector FastAPI career preparation",
    )

    stored = await DocumentRepository(db_session).get_document(result.document.id, "user-a")
    assert stored is not None
    assert stored.processing_status == "completed"
    assert result.chunk_count > 0
    assert (storage_dir / stored.storage_path).read_bytes().startswith(b"Python")


async def test_semantic_retrieval_is_scoped_by_owner_and_document(db_session, storage_dir) -> None:
    provider = DeterministicEmbeddingProvider(dimensions=256)
    ingestion_service = DocumentIngestionService(
        repository=DocumentRepository(db_session),
        parsers=DocumentParserRegistry(),
        chunker=DeterministicTextChunker(chunk_size=200, chunk_overlap=20),
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

    search_service = DocumentSearchService(DocumentRepository(db_session), provider)
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
