from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.documents import get_management_service
from app.db.models.document import DocumentChunk
from app.db.repositories.documents import DocumentRepository
from app.integrations.storage.local import LocalDocumentStorage
from app.main import create_app
from app.rag.chunking import DeterministicTextChunker
from app.rag.embeddings import DeterministicEmbeddingProvider
from app.rag.parsers import DocumentParserRegistry
from app.services.document_service import DocumentIngestionService, DocumentManagementService


def _ingestion_service(
    db_session: AsyncSession, storage_dir, provider: DeterministicEmbeddingProvider | None = None
) -> DocumentIngestionService:
    return DocumentIngestionService(
        repository=DocumentRepository(db_session),
        parsers=DocumentParserRegistry(),
        chunker=DeterministicTextChunker(chunk_size=24, chunk_overlap=4),
        embedding_provider=provider or DeterministicEmbeddingProvider(dimensions=256),
        storage=LocalDocumentStorage(storage_dir),
    )


async def _create_document(
    db_session: AsyncSession, storage_dir, *, owner_id: str, filename: str = "document.txt"
):
    return await _ingestion_service(db_session, storage_dir).ingest(
        owner_id=owner_id,
        filename=filename,
        mime_type="text/plain",
        content=b"Python PostgreSQL pgvector FastAPI document content",
    )


@pytest.mark.asyncio
async def test_owner_can_delete_existing_document(
    db_session: AsyncSession,
    tmp_path,
) -> None:
    # Arrange
    repository = DocumentRepository(db_session)
    storage = LocalDocumentStorage(tmp_path)

    document_id = uuid4()
    owner_id = "owner-1"

    _document = await repository.create_document(
        document_id=document_id,
        owner_id=owner_id,
        filename="test.txt",
        mime_type="text/plain",
        document_type="txt",
        size_bytes=10,
        checksum="test-checksum",
        storage_path="test.txt",
    )
    service = DocumentManagementService(
        repository=repository,
        storage=storage,
    )

    # Act
    deleted = await service.delete_document(
        document_id,
        owner_id,
    )

    # Assert
    assert deleted is True

    document_after_delete = await repository.get_document(
        document_id,
        owner_id,
    )

    assert document_after_delete is None


async def test_dd_002_delete_cascades_document_chunks(
    db_session: AsyncSession, storage_dir
) -> None:
    ingested = await _create_document(db_session, storage_dir, owner_id="owner-1")
    document_id = ingested.document.id

    deleted = await DocumentManagementService(
        repository=DocumentRepository(db_session), storage=LocalDocumentStorage(storage_dir)
    ).delete_document(document_id, "owner-1")

    remaining_chunks = await db_session.scalars(
        select(DocumentChunk).where(DocumentChunk.document_id == document_id)
    )
    assert deleted is True
    assert remaining_chunks.all() == []


async def test_dd_003_delete_removes_source_file(db_session: AsyncSession, storage_dir) -> None:
    ingested = await _create_document(db_session, storage_dir, owner_id="owner-1")
    source_file = storage_dir / ingested.document.storage_path
    assert source_file.exists()

    deleted = await DocumentManagementService(
        repository=DocumentRepository(db_session), storage=LocalDocumentStorage(storage_dir)
    ).delete_document(ingested.document.id, "owner-1")

    assert deleted is True
    assert not source_file.exists()


async def test_dd_004_other_owner_cannot_delete_document_or_chunks_or_file(
    db_session: AsyncSession, storage_dir
) -> None:
    ingested = await _create_document(db_session, storage_dir, owner_id="owner-1")
    source_file = storage_dir / ingested.document.storage_path

    deleted = await DocumentManagementService(
        repository=DocumentRepository(db_session), storage=LocalDocumentStorage(storage_dir)
    ).delete_document(ingested.document.id, "owner-2")

    document = await DocumentRepository(db_session).get_document(ingested.document.id, "owner-1")
    chunks = await db_session.scalars(
        select(DocumentChunk).where(DocumentChunk.document_id == ingested.document.id)
    )
    assert deleted is False
    assert document is not None
    assert chunks.all()
    assert source_file.exists()


async def test_dd_005_deleting_nonexistent_document_does_not_modify_existing_data(
    db_session: AsyncSession, storage_dir
) -> None:
    ingested = await _create_document(db_session, storage_dir, owner_id="owner-1")

    deleted = await DocumentManagementService(
        repository=DocumentRepository(db_session), storage=LocalDocumentStorage(storage_dir)
    ).delete_document(uuid4(), "owner-1")

    assert deleted is False
    assert await DocumentRepository(db_session).get_document(ingested.document.id, "owner-1")
    assert (storage_dir / ingested.document.storage_path).exists()


async def test_dd_006_missing_source_file_does_not_prevent_database_cleanup(
    db_session: AsyncSession, storage_dir
) -> None:
    ingested = await _create_document(db_session, storage_dir, owner_id="owner-1")
    source_file = storage_dir / ingested.document.storage_path
    source_file.unlink()

    deleted = await DocumentManagementService(
        repository=DocumentRepository(db_session), storage=LocalDocumentStorage(storage_dir)
    ).delete_document(ingested.document.id, "owner-1")

    document = await DocumentRepository(db_session).get_document(ingested.document.id, "owner-1")
    chunks = await db_session.scalars(
        select(DocumentChunk).where(DocumentChunk.document_id == ingested.document.id)
    )
    assert deleted is True
    assert document is None
    assert chunks.all() == []


async def test_dd_009_delete_api_returns_204_without_response_body(
    db_session: AsyncSession, storage_dir
) -> None:
    ingested = await _create_document(db_session, storage_dir, owner_id="owner-1")
    management_service = DocumentManagementService(
        repository=DocumentRepository(db_session), storage=LocalDocumentStorage(storage_dir)
    )
    app = create_app()
    app.dependency_overrides[get_management_service] = lambda: management_service

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.delete(
                f"/api/v1/documents/{ingested.document.id}",
                headers={"X-Internal-User-ID": "owner-1"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    assert response.content == b""
    assert (
        await DocumentRepository(db_session).get_document(ingested.document.id, "owner-1")
    ) is None


async def test_dd_010_delete_api_returns_not_found_for_missing_or_other_owner_document(
    db_session: AsyncSession, storage_dir
) -> None:
    ingested = await _create_document(db_session, storage_dir, owner_id="owner-1")
    source_file = storage_dir / ingested.document.storage_path
    management_service = DocumentManagementService(
        repository=DocumentRepository(db_session), storage=LocalDocumentStorage(storage_dir)
    )
    app = create_app()
    app.dependency_overrides[get_management_service] = lambda: management_service

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            missing_response = await client.delete(
                f"/api/v1/documents/{uuid4()}",
                headers={"X-Internal-User-ID": "owner-1"},
            )
            other_owner_response = await client.delete(
                f"/api/v1/documents/{ingested.document.id}",
                headers={"X-Internal-User-ID": "owner-2"},
            )
    finally:
        app.dependency_overrides.clear()

    assert missing_response.status_code == 404
    assert other_owner_response.status_code == 404
    assert missing_response.json() == {"detail": "Document not found"}
    assert other_owner_response.json() == {"detail": "Document not found"}
    assert await DocumentRepository(db_session).get_document(ingested.document.id, "owner-1")
    assert source_file.exists()
