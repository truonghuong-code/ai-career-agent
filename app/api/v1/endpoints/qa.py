from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_placeholder_owner_id
from app.core.config import get_settings
from app.db.repositories.documents import DocumentRepository
from app.db.session import get_db_session
from app.integrations.llm.provider import LLMProviderError, LLMTimeoutError, create_llm_provider
from app.rag.context import ContextBuilder
from app.rag.embeddings import create_embedding_provider
from app.schemas.qa import QARequest, QAResponse, QASource
from app.services.document_service import DocumentSearchService
from app.services.qa_service import GroundedQAService, QAEmbeddingError, QARetrievalError

router = APIRouter(prefix="/qa")
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
OwnerDep = Annotated[str, Depends(get_placeholder_owner_id)]


def get_qa_service(session: SessionDep) -> GroundedQAService:
    try:
        settings = get_settings()
        return GroundedQAService(
            search_service=DocumentSearchService(
                DocumentRepository(session), create_embedding_provider(settings)
            ),
            llm_provider=create_llm_provider(settings),
            context_builder=ContextBuilder(settings.qa_max_context_chunks),
            timeout_seconds=settings.llm_timeout_seconds,
        )
    except ValueError as exc:
        raise HTTPException(503, "Question answering is not configured") from exc


@router.post("", response_model=QAResponse)
async def answer_question(
    request: QARequest,
    owner_id: OwnerDep,
    service: Annotated[GroundedQAService, Depends(get_qa_service)],
) -> QAResponse:
    try:
        result = await service.answer(
            owner_id=owner_id,
            question=request.question,
            limit=request.limit,
            document_ids=request.document_ids,
        )
    except LLMTimeoutError as exc:
        raise HTTPException(504, "Answer generation timed out") from exc
    except LLMProviderError as exc:
        raise HTTPException(502, "Answer generation failed") from exc
    except QAEmbeddingError as exc:
        raise HTTPException(502, "Question retrieval failed") from exc
    except QARetrievalError as exc:
        raise HTTPException(503, "Question retrieval unavailable") from exc
    return QAResponse(
        answer=result.answer,
        status=result.status,
        sources=[QASource.model_validate(source) for source in result.sources],
    )
