from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.documents import get_management_service
from app.db.models.document import Document
from app.db.repositories.documents import DocumentRepository
from app.integrations.storage.local import LocalDocumentStorage
from app.main import create_app
from app.services.document_service import DocumentManagementService


async def _create_document(
    repository: DocumentRepository,
    *,
    owner_id: str,
    filename: str,
    created_at: datetime,
) -> Document:
    document = await repository.create_document(
        document_id=uuid4(),
        owner_id=owner_id,
        filename=filename,
        mime_type="text/plain",
        document_type="txt",
        size_bytes=12,
        checksum=f"checksum-{filename}",
        storage_path=f"{filename}.txt",
    )
    await repository.session.execute(
        update(Document).where(Document.id == document.id).values(created_at=created_at)
    )
    await repository.session.commit()
    await repository.session.refresh(document)
    return document


async def test_dl_001_listing_is_owner_scoped_and_includes_management_statuses(
    db_session: AsyncSession, storage_dir
) -> None:
    repository = DocumentRepository(db_session)
    now = datetime.now(UTC)
    processing = await _create_document(
        repository, owner_id="owner-a", filename="processing", created_at=now
    )
    completed = await _create_document(
        repository, owner_id="owner-a", filename="completed", created_at=now - timedelta(minutes=1)
    )
    failed = await _create_document(
        repository, owner_id="owner-a", filename="failed", created_at=now - timedelta(minutes=2)
    )
    await repository.complete_document(completed, extracted_text_length=100)
    await repository.fail_document(failed, "Parser failed")
    await _create_document(
        repository, owner_id="owner-b", filename="private", created_at=now - timedelta(minutes=3)
    )

    documents = await DocumentManagementService(
        repository=repository, storage=LocalDocumentStorage(storage_dir)
    ).list_documents("owner-a")

    assert {document.id for document in documents} == {processing.id, completed.id, failed.id}
    assert {document.processing_status for document in documents} == {
        "processing",
        "completed",
        "failed",
    }
    assert completed.extracted_text_length == 100
    assert failed.error_message == "Parser failed"


async def test_dl_002_listing_uses_created_at_then_id_descending_order(
    db_session: AsyncSession, storage_dir
) -> None:
    repository = DocumentRepository(db_session)
    newest_time = datetime.now(UTC)
    oldest = await _create_document(
        repository,
        owner_id="owner-a",
        filename="oldest",
        created_at=newest_time - timedelta(minutes=1),
    )
    first_at_same_time = await _create_document(
        repository, owner_id="owner-a", filename="same-time-one", created_at=newest_time
    )
    second_at_same_time = await _create_document(
        repository, owner_id="owner-a", filename="same-time-two", created_at=newest_time
    )

    documents = await DocumentManagementService(
        repository=repository, storage=LocalDocumentStorage(storage_dir)
    ).list_documents("owner-a")

    expected_same_time = sorted([first_at_same_time.id, second_at_same_time.id], reverse=True)
    assert [document.id for document in documents] == [*expected_same_time, oldest.id]


async def test_dl_003_list_api_returns_document_metadata(
    db_session: AsyncSession, storage_dir
) -> None:
    repository = DocumentRepository(db_session)
    document = await _create_document(
        repository,
        owner_id="owner-a",
        filename="metadata",
        created_at=datetime.now(UTC),
    )
    management_service = DocumentManagementService(
        repository=repository, storage=LocalDocumentStorage(storage_dir)
    )
    app = create_app()
    app.dependency_overrides[get_management_service] = lambda: management_service

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.get(
                "/api/v1/documents", headers={"X-Internal-User-ID": "owner-a"}
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    returned = response.json()["documents"]
    assert len(returned) == 1
    assert returned[0] == {
        "id": str(document.id),
        "owner_id": "owner-a",
        "filename": "metadata",
        "mime_type": "text/plain",
        "document_type": "txt",
        "size_bytes": 12,
        "checksum": "checksum-metadata",
        "processing_status": "processing",
        "extracted_text_length": None,
        "error_message": None,
        "created_at": document.created_at.isoformat().replace("+00:00", "Z"),
        "updated_at": document.updated_at.isoformat().replace("+00:00", "Z"),
    }


async def test_dl_004_list_api_does_not_return_another_owners_documents(
    db_session: AsyncSession, storage_dir
) -> None:
    repository = DocumentRepository(db_session)
    now = datetime.now(UTC)
    own_document = await _create_document(
        repository, owner_id="owner-a", filename="visible", created_at=now
    )
    other_document = await _create_document(
        repository, owner_id="owner-b", filename="private", created_at=now
    )
    management_service = DocumentManagementService(
        repository=repository, storage=LocalDocumentStorage(storage_dir)
    )
    app = create_app()
    app.dependency_overrides[get_management_service] = lambda: management_service

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.get(
                "/api/v1/documents", headers={"X-Internal-User-ID": "owner-a"}
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    returned = response.json()["documents"]
    assert [item["id"] for item in returned] == [str(own_document.id)]
    assert str(other_document.id) not in {item["id"] for item in returned}
    assert "private" not in {item["filename"] for item in returned}
