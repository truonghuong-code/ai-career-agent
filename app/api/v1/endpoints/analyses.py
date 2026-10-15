from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_placeholder_owner_id
from app.core.config import get_settings
from app.db.repositories.analyses import AnalysisRepository
from app.db.session import get_db_session
from app.integrations.llm.analysis import create_analysis_provider
from app.integrations.llm.provider import LLMProviderError, LLMTimeoutError
from app.schemas.analysis import (
    AnalysisKind,
    AnalysisListResponse,
    AnalysisRequest,
    AnalysisResponse,
)
from app.services.analysis_service import (
    AnalysisNoContentError,
    AnalysisNotFoundError,
    AnalysisNotReadyError,
    AnalysisService,
    AnalysisStorageError,
    AnalysisTooLargeError,
)

router = APIRouter()
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]


async def get_analysis_owner(
    owner_id: Annotated[str, Depends(get_placeholder_owner_id)],
) -> str:
    if len(owner_id) > 128:
        raise HTTPException(400, "Internal user ID is too long")
    return owner_id


OwnerDep = Annotated[str, Depends(get_analysis_owner)]


def get_analysis_reader(session: SessionDep) -> AnalysisService:
    return AnalysisService(AnalysisRepository(session))


def get_analysis_service(session: SessionDep) -> AnalysisService:
    try:
        settings = get_settings()
        return AnalysisService(
            AnalysisRepository(session),
            create_analysis_provider(settings),
            provider_name=settings.llm_provider,
            model_name=settings.llm_model if settings.llm_provider == "openai" else "fake",
            timeout_seconds=settings.llm_timeout_seconds,
            max_context_chars=settings.analysis_max_context_chars,
            max_output_tokens=settings.analysis_max_output_tokens,
        )
    except ValueError as exc:
        raise HTTPException(503, "Analysis generation is not configured") from exc


def _http_error(exc: Exception) -> HTTPException:
    mapping = (
        (AnalysisNotFoundError, 404, "Resource not found"),
        (AnalysisNotReadyError, 409, "Document is not ready or changed during analysis"),
        (AnalysisNoContentError, 422, "Document has no usable text"),
        (AnalysisTooLargeError, 413, "Document exceeds analysis context budget"),
        (LLMTimeoutError, 504, "Analysis generation timed out"),
        (LLMProviderError, 502, "Analysis generation failed"),
        (AnalysisStorageError, 503, "Analysis storage unavailable"),
    )
    for error_type, status, detail in mapping:
        if isinstance(exc, error_type):
            return HTTPException(status, detail)
    return HTTPException(500, "Analysis operation failed")


ANALYSIS_ERRORS = (
    AnalysisNotFoundError,
    AnalysisNotReadyError,
    AnalysisNoContentError,
    AnalysisTooLargeError,
    LLMProviderError,
    AnalysisStorageError,
)


@router.post("/documents/{document_id}/analyses", response_model=AnalysisResponse, status_code=201)
async def create_analysis(
    document_id: UUID,
    request: AnalysisRequest,
    owner_id: OwnerDep,
    service: Annotated[AnalysisService, Depends(get_analysis_service)],
) -> AnalysisResponse:
    try:
        return await service.create(document_id, owner_id, request.kind)
    except ANALYSIS_ERRORS as exc:
        raise _http_error(exc) from exc


@router.get("/documents/{document_id}/analyses", response_model=AnalysisListResponse)
async def list_analyses(
    document_id: UUID,
    owner_id: OwnerDep,
    service: Annotated[AnalysisService, Depends(get_analysis_reader)],
    kind: AnalysisKind | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AnalysisListResponse:
    try:
        return AnalysisListResponse(
            analyses=await service.list(
                document_id,
                owner_id,
                kind,
                limit,
                offset,
            )
        )
    except ANALYSIS_ERRORS as exc:
        raise _http_error(exc) from exc


@router.get("/analyses/{analysis_id}", response_model=AnalysisResponse)
async def get_analysis(
    analysis_id: UUID,
    owner_id: OwnerDep,
    service: Annotated[AnalysisService, Depends(get_analysis_reader)],
) -> AnalysisResponse:
    try:
        return await service.get(analysis_id, owner_id)
    except ANALYSIS_ERRORS as exc:
        raise _http_error(exc) from exc
