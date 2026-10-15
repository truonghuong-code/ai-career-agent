from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.analysis import DocumentAnalysis
from app.db.models.document import Document, DocumentChunk, DocumentStatus
from app.schemas.analysis import (
    AnalysisKind,
    AnalysisProvenance,
    AnalysisResponse,
    AnalysisSource,
    AnalysisSummary,
    CVProfile,
    JDProfile,
)


@dataclass(frozen=True)
class AnalysisChunk:
    id: UUID
    document_id: UUID
    chunk_index: int
    text: str


@dataclass(frozen=True)
class AnalysisInput:
    document_id: UUID
    checksum: str
    status: str
    chunks: tuple[AnalysisChunk, ...]


class AnalysisInputChangedError(RuntimeError):
    """Source document changed or disappeared while generation was running."""


class AnalysisRepository:
    """Owns transaction boundaries; use a dedicated request/session for this workflow."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def load_input(self, document_id: UUID, owner_id: str) -> AnalysisInput | None:
        try:
            row = (
                await self.session.execute(
                    select(
                        Document.id,
                        Document.checksum,
                        Document.processing_status,
                    ).where(Document.id == document_id, Document.owner_id == owner_id)
                )
            ).one_or_none()
            if row is None:
                return None
            chunks = (
                await self.session.execute(
                    select(
                        DocumentChunk.id,
                        DocumentChunk.document_id,
                        DocumentChunk.chunk_index,
                        DocumentChunk.text,
                    )
                    .join(Document)
                    .where(
                        Document.id == document_id,
                        Document.owner_id == owner_id,
                        DocumentChunk.owner_id == owner_id,
                        Document.processing_status == DocumentStatus.COMPLETED.value,
                    )
                    .order_by(DocumentChunk.chunk_index, DocumentChunk.id)
                )
            ).all()
            return AnalysisInput(
                row.id,
                row.checksum,
                row.processing_status,
                tuple(AnalysisChunk(*chunk) for chunk in chunks),
            )
        finally:
            # No transaction or connection remains occupied during the model call.
            await self.session.rollback()

    async def save(
        self,
        *,
        document_id: UUID,
        owner_id: str,
        kind: AnalysisKind,
        checksum: str,
        profile: CVProfile | JDProfile,
        sources: list[AnalysisSource],
        provenance: AnalysisProvenance,
        status: str,
    ) -> AnalysisResponse:
        try:
            row = (
                await self.session.execute(
                    select(
                        Document.checksum,
                        Document.processing_status,
                    )
                    .where(Document.id == document_id, Document.owner_id == owner_id)
                    .with_for_update()
                )
            ).one_or_none()
            if row is None or row.checksum != checksum or row.processing_status != "completed":
                raise AnalysisInputChangedError("Analysis source changed")
            previous = await self.session.scalar(
                select(func.max(DocumentAnalysis.version)).where(
                    DocumentAnalysis.document_id == document_id,
                    DocumentAnalysis.kind == kind,
                    DocumentAnalysis.owner_id == owner_id,
                )
            )
            record = DocumentAnalysis(
                document_id=document_id,
                owner_id=owner_id,
                kind=kind,
                version=(previous or 0) + 1,
                status=status,
                document_checksum=checksum,
                profile=profile.model_dump(mode="json"),
                sources=[source.model_dump(mode="json") for source in sources],
                provenance=provenance.model_dump(mode="json"),
            )
            self.session.add(record)
            await self.session.flush()
            result = AnalysisResponse.model_validate(record)
            await self.session.commit()
            return result
        except BaseException:
            await self.session.rollback()
            raise

    async def get(self, analysis_id: UUID, owner_id: str) -> AnalysisResponse | None:
        record = await self.session.scalar(
            select(DocumentAnalysis)
            .join(Document)
            .where(
                DocumentAnalysis.id == analysis_id,
                DocumentAnalysis.owner_id == owner_id,
                Document.owner_id == owner_id,
            )
        )
        return AnalysisResponse.model_validate(record) if record is not None else None

    async def list(
        self,
        document_id: UUID,
        owner_id: str,
        kind: AnalysisKind | None,
        limit: int,
        offset: int,
    ) -> list[AnalysisSummary] | None:
        exists = await self.session.scalar(
            select(Document.id).where(
                Document.id == document_id,
                Document.owner_id == owner_id,
            )
        )
        if exists is None:
            return None
        # Select metadata only: listing history never loads large profile/prompt JSONB.
        statement = (
            select(
                DocumentAnalysis.id,
                DocumentAnalysis.document_id,
                DocumentAnalysis.kind,
                DocumentAnalysis.version,
                DocumentAnalysis.status,
                DocumentAnalysis.document_checksum,
                DocumentAnalysis.created_at,
            )
            .join(Document)
            .where(
                DocumentAnalysis.document_id == document_id,
                DocumentAnalysis.owner_id == owner_id,
                Document.owner_id == owner_id,
            )
            .order_by(DocumentAnalysis.created_at.desc(), DocumentAnalysis.id.desc())
        )
        if kind is not None:
            statement = statement.where(DocumentAnalysis.kind == kind)
        rows = (await self.session.execute(statement.limit(limit).offset(offset))).all()
        return [AnalysisSummary.model_validate(row) for row in rows]
