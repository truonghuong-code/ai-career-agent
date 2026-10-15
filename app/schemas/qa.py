from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class QARequest(BaseModel):
    question: str = Field(min_length=1, max_length=5000)
    limit: int = Field(default=5, ge=1, le=20, strict=True)
    document_ids: list[UUID] | None = None

    @field_validator("question", mode="before")
    @classmethod
    def normalize_question(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class QASource(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    number: int = Field(ge=1)
    document_id: UUID
    chunk_id: UUID
    chunk_index: int = Field(ge=0)


class QAResponse(BaseModel):
    answer: str
    status: Literal["answered", "no_context", "insufficient_evidence"]
    sources: list[QASource]
