from pathlib import Path
from uuid import UUID


class LocalDocumentStorage:
    """Filesystem-backed document storage for local development and Docker volumes."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir

    def save(self, document_id: UUID, filename: str, content: bytes) -> str:
        safe_filename = Path(filename).name
        relative_path = Path(str(document_id)) / safe_filename
        destination = self.base_dir / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        return str(relative_path)

    def delete(self, storage_path: str) -> None:
        base_dir = self.base_dir.resolve()
        path = (self.base_dir / storage_path).resolve()
        try:
            path.relative_to(base_dir)
        except ValueError as exc:
            raise ValueError("Storage path must be inside the configured base directory") from exc
        if path.exists():
            path.unlink()
