from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.integrations.storage.local import LocalDocumentStorage
from app.services.document_service import DocumentManagementService


def test_dd_007_storage_delete_rejects_path_outside_base_directory(tmp_path: Path) -> None:
    storage_root = tmp_path / "uploads"
    external_file = tmp_path / "important.txt"
    external_file.write_text("keep me")

    with pytest.raises(ValueError):
        LocalDocumentStorage(storage_root).delete("../important.txt")

    assert external_file.read_text() == "keep me"


async def test_dd_008_filesystem_errors_are_propagated() -> None:
    document = SimpleNamespace(storage_path="owner-1/document.txt")
    repository = SimpleNamespace(
        get_document=AsyncMock(return_value=document),
        delete_document=AsyncMock(return_value=True),
    )
    storage = SimpleNamespace(delete=lambda _: (_ for _ in ()).throw(PermissionError("denied")))

    with pytest.raises(PermissionError, match="denied"):
        await DocumentManagementService(repository=repository, storage=storage).delete_document(
            uuid4(), "owner-1"
        )

    repository.delete_document.assert_awaited_once()
