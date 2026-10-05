from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_placeholder_owner_id
from app.core.config import get_settings
from app.db.repositories.documents import DocumentRepository
from app.db.session import get_db_session
from app.integrations.storage.local import LocalDocumentStorage
from app.rag.chunking import DeterministicTextChunker
from app.rag.embeddings import EmbeddingProviderError, create_embedding_provider
from app.rag.parsers import (
    DocumentExtractionError,
    DocumentParserRegistry,
    UnsupportedDocumentTypeError,
)
from app.schemas.documents import (
    DocumentListResponse,
    DocumentResponse,
    DocumentSearchRequest,
    DocumentSearchResponse,
    DocumentSearchResult,
)
from app.services.document_service import (
    DocumentIngestionError,
    DocumentIngestionService,
    DocumentManagementService,
    DocumentSearchService,
)

router = APIRouter(prefix="/documents")
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
OwnerDep = Annotated[str, Depends(get_placeholder_owner_id)]


def get_ingestion_service(session: SessionDep) -> DocumentIngestionService:
    settings = get_settings()
    return DocumentIngestionService(
        repository=DocumentRepository(session),
        parsers=DocumentParserRegistry(),
        chunker=DeterministicTextChunker(),
        embedding_provider=create_embedding_provider(settings),
        storage=LocalDocumentStorage(settings.document_storage_dir),
    )


def get_search_service(session: SessionDep) -> DocumentSearchService:
    return DocumentSearchService(
        repository=DocumentRepository(session),
        embedding_provider=create_embedding_provider(get_settings()),
    )


def get_management_service(session: SessionDep) -> DocumentManagementService:
    return DocumentManagementService(
        repository=DocumentRepository(session),
        storage=LocalDocumentStorage(get_settings().document_storage_dir),
    )


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    owner_id: OwnerDep,
    service: Annotated[DocumentManagementService, Depends(get_management_service)],
) -> DocumentListResponse:
    documents = await service.list_documents(owner_id)
    return DocumentListResponse(
        documents=[DocumentResponse.model_validate(document) for document in documents]
    )


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    owner_id: OwnerDep,
    file: Annotated[UploadFile, File(description="PDF, DOCX, TXT, or Markdown document")],
    service: Annotated[DocumentIngestionService, Depends(get_ingestion_service)],
) -> DocumentResponse:
    settings = get_settings()
    content = await file.read()
    if len(content) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large"
        )
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="File must not be empty"
        )
    try:
        result = await service.ingest(
            owner_id=owner_id,
            filename=file.filename or "upload",
            mime_type=file.content_type or "",
            content=content,
        )
    except UnsupportedDocumentTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)
        ) from exc
    except DocumentExtractionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except EmbeddingProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except DocumentIngestionError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Document processing failed"
        ) from exc
    return DocumentResponse.model_validate(result.document)


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID, owner_id: OwnerDep, session: SessionDep
) -> DocumentResponse:
    document = await DocumentRepository(session).get_document(document_id, owner_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return DocumentResponse.model_validate(document)


@router.post("/search", response_model=DocumentSearchResponse)
async def search_documents(
    request: DocumentSearchRequest,
    owner_id: OwnerDep,
    service: Annotated[DocumentSearchService, Depends(get_search_service)],
) -> DocumentSearchResponse:
    try:
        matches = await service.search(
            owner_id=owner_id,
            query=request.query,
            limit=request.limit,
            document_ids=request.document_ids,
        )
    except EmbeddingProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return DocumentSearchResponse(
        results=[
            DocumentSearchResult(
                chunk_id=match.chunk.id,
                document_id=match.chunk.document_id,
                filename=match.chunk.document.filename,
                document_type=match.chunk.document.document_type,
                chunk_index=match.chunk.chunk_index,
                text=match.chunk.text,
                char_start=match.chunk.char_start,
                char_end=match.chunk.char_end,
                score=match.score,
                source_metadata=match.chunk.chunk_metadata,
            )
            for match in matches
        ]
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID,
    owner_id: OwnerDep,
    service: Annotated[DocumentManagementService, Depends(get_management_service)],
) -> None:
    deleted = await service.delete_document(document_id, owner_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
