from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.document import Document, DocumentChunk, DocumentStatus
from app.rag.chunking import TextChunk


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: DocumentChunk
    score: float


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_document(
        self,
        *,
        owner_id: str,
        document_id: UUID,
        filename: str,
        mime_type: str,
        document_type: str,
        size_bytes: int,
        checksum: str,
        storage_path: str,
    ) -> Document:
        document = Document(
            id=document_id,
            owner_id=owner_id,
            filename=filename,
            mime_type=mime_type,
            document_type=document_type,
            size_bytes=size_bytes,
            checksum=checksum,
            storage_path=storage_path,
            processing_status=DocumentStatus.PROCESSING.value,
        )
        self.session.add(document)
        await self.session.commit()
        await self.session.refresh(document)
        return document

    async def complete_document(self, document: Document, extracted_text_length: int) -> None:
        document.processing_status = DocumentStatus.COMPLETED.value
        document.extracted_text_length = extracted_text_length
        document.error_message = None
        await self.session.commit()
        await self.session.refresh(document)

    async def fail_document(self, document: Document, message: str) -> None:
        document.processing_status = DocumentStatus.FAILED.value
        document.error_message = message
        await self.session.commit()

    async def add_chunks(
        self,
        *,
        document: Document,
        chunks: Sequence[TextChunk],
        embeddings: Sequence[list[float]],
        extraction_metadata: dict[str, int | str],
    ) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("The number of chunks and embeddings must match")
        self.session.add_all(
            [
                DocumentChunk(
                    document_id=document.id,
                    owner_id=document.owner_id,
                    chunk_index=chunk.index,
                    text=chunk.text,
                    char_start=chunk.char_start,
                    char_end=chunk.char_end,
                    chunk_metadata=extraction_metadata,
                    embedding=embedding,
                )
                for chunk, embedding in zip(chunks, embeddings, strict=True)
            ]
        )
        await self.session.flush()

    async def get_document(self, document_id: UUID, owner_id: str) -> Document | None:
        result = await self.session.execute(
            select(Document).where(Document.id == document_id, Document.owner_id == owner_id)
        )
        return result.scalar_one_or_none()

    async def search(
        self,
        *,
        owner_id: str,
        query_embedding: list[float],
        limit: int,
        document_ids: Sequence[UUID] | None = None,
    ) -> list[RetrievedChunk]:
        distance = DocumentChunk.embedding.cosine_distance(query_embedding).label("distance")
        statement = (
            select(DocumentChunk, distance)
            .join(Document)
            .options(selectinload(DocumentChunk.document))
            .where(
                DocumentChunk.owner_id == owner_id,
                Document.owner_id == owner_id,
                Document.processing_status == DocumentStatus.COMPLETED.value,
            )
            .order_by(distance)
            .limit(limit)
        )
        if document_ids:
            statement = statement.where(DocumentChunk.document_id.in_(document_ids))
        result = await self.session.execute(statement)
        return [
            RetrievedChunk(chunk=chunk, score=1 - float(distance))
            for chunk, distance in result.all()
        ]

    async def rollback(self) -> None:
        await self.session.rollback()
