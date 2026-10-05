import hashlib
import logging
from dataclasses import dataclass
from uuid import UUID, uuid4

from app.db.models.document import Document
from app.db.repositories.documents import DocumentRepository, RetrievedChunk
from app.integrations.storage.local import LocalDocumentStorage
from app.rag.chunking import DeterministicTextChunker
from app.rag.embeddings import EmbeddingProvider, EmbeddingProviderError
from app.rag.parsers import DocumentExtractionError, DocumentParserRegistry

logger = logging.getLogger(__name__)


class DocumentIngestionError(RuntimeError):
    """Raised when a supported document fails during ingestion."""


@dataclass(frozen=True)
class IngestedDocument:
    document: Document
    chunk_count: int


class DocumentIngestionService:
    def __init__(
        self,
        repository: DocumentRepository,
        parsers: DocumentParserRegistry,
        chunker: DeterministicTextChunker,
        embedding_provider: EmbeddingProvider,
        storage: LocalDocumentStorage,
    ) -> None:
        self.repository = repository
        self.parsers = parsers
        self.chunker = chunker
        self.embedding_provider = embedding_provider
        self.storage = storage

    async def ingest(
        self, *, owner_id: str, filename: str, mime_type: str, content: bytes
    ) -> IngestedDocument:
        document_type, parser = self.parsers.get_parser(filename, mime_type)
        checksum = hashlib.sha256(content).hexdigest()
        document_id = uuid4()
        storage_path = self.storage.save(document_id, filename, content)
        document = await self.repository.create_document(
            owner_id=owner_id,
            document_id=document_id,
            filename=filename,
            mime_type=mime_type,
            document_type=document_type,
            size_bytes=len(content),
            checksum=checksum,
            storage_path=storage_path,
        )
        try:
            extracted = parser.extract(content)
            chunks = self.chunker.split(extracted.text)
            embeddings = await self.embedding_provider.embed([chunk.text for chunk in chunks])
            await self.repository.add_chunks(
                document=document,
                chunks=chunks,
                embeddings=embeddings,
                extraction_metadata=extracted.metadata,
            )
            await self.repository.complete_document(document, len(extracted.text))
            logger.info(
                "document_ingested document_id=%s owner_id=%s chunks=%s",
                document.id,
                owner_id,
                len(chunks),
            )
            return IngestedDocument(document=document, chunk_count=len(chunks))
        except (DocumentExtractionError, EmbeddingProviderError) as exc:
            logger.warning(
                "document_ingestion_failed document_id=%s error=%s",
                document.id,
                exc,
            )
            await self.repository.rollback()
            await self.repository.fail_document(document, str(exc))
            raise
        except Exception as exc:
            logger.exception(
                "document_ingestion_failed document_id=%s",
                document.id,
            )
            await self.repository.rollback()
            await self.repository.fail_document(document, str(exc))
            raise DocumentIngestionError("Document processing failed") from exc


class DocumentSearchService:
    def __init__(
        self, repository: DocumentRepository, embedding_provider: EmbeddingProvider
    ) -> None:
        self.repository = repository
        self.embedding_provider = embedding_provider

    async def search(
        self,
        *,
        owner_id: str,
        query: str,
        limit: int,
        document_ids: list[UUID] | None,
    ) -> list[RetrievedChunk]:
        embedding = (await self.embedding_provider.embed([query]))[0]
        return await self.repository.search(
            owner_id=owner_id,
            query_embedding=embedding,
            limit=limit,
            document_ids=document_ids,
        )
