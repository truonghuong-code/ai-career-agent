from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: str
    filename: str
    mime_type: str
    document_type: str
    size_bytes: int
    checksum: str
    processing_status: str
    extracted_text_length: int | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class DocumentSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=5_000)
    document_ids: list[UUID] | None = None
    limit: int = Field(default=5, ge=1, le=20)


class DocumentSearchResult(BaseModel):
    chunk_id: UUID
    document_id: UUID
    filename: str
    document_type: str
    chunk_index: int
    text: str
    char_start: int
    char_end: int
    score: float
    source_metadata: dict[str, int | str]


class DocumentSearchResponse(BaseModel):
    results: list[DocumentSearchResult]
