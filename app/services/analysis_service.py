import asyncio
import logging
import math
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.db.repositories.analyses import AnalysisInputChangedError, AnalysisRepository
from app.db.repositories.documents import RetrievedChunk
from app.integrations.llm.analysis import AnalysisProvider
from app.integrations.llm.provider import LLMProviderError, LLMTimeoutError
from app.rag.context import BuiltContext, ContextBuilder
from app.schemas.analysis import (
    AnalysisKind,
    AnalysisMessage,
    AnalysisProvenance,
    AnalysisResponse,
    AnalysisSource,
    AnalysisSummary,
    CVProfile,
    JDProfile,
)
from app.services.analysis_prompt import PROMPT_VERSION, SCHEMA_VERSION, build_analysis_prompt

logger = logging.getLogger(__name__)


class AnalysisNotFoundError(RuntimeError):
    """Missing resource or resource outside the requesting ownership scope."""


class AnalysisNotReadyError(RuntimeError):
    """Document is not completed or changed during generation."""


class AnalysisNoContentError(RuntimeError):
    """No usable document content is available."""


class AnalysisTooLargeError(RuntimeError):
    """Whole-document context exceeds the configured budget."""


class AnalysisStorageError(RuntimeError):
    """Analysis storage is unavailable."""


def validate_profile(
    profile: object,
    kind: AnalysisKind,
    context: BuiltContext,
) -> CVProfile | JDProfile:
    model = CVProfile if kind == "cv" else JDProfile
    try:
        # Revalidate substitute providers too; never trust model_construct or mutated models.
        parsed = model.model_validate(profile)
    except ValidationError as exc:
        raise LLMProviderError("Invalid analysis response") from exc
    sources = {source.number: source.text for source in context.sources}
    for field in model.model_fields:
        for fact in getattr(parsed, field):
            for evidence in fact.evidence:
                text = sources.get(evidence.source_number)
                if text is None or evidence.quote not in text:
                    raise LLMProviderError("Invalid analysis evidence")
    return parsed


class AnalysisService:
    def __init__(
        self,
        repository: AnalysisRepository,
        provider: AnalysisProvider | None = None,
        *,
        provider_name: str = "fake",
        model_name: str = "fake",
        timeout_seconds: float = 30,
        max_context_chars: int = 40000,
        max_output_tokens: int = 4096,
    ) -> None:
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("Analysis timeout must be positive and finite")
        if type(max_context_chars) is not int or max_context_chars <= 0:
            raise ValueError("Analysis context budget must be positive")
        if type(max_output_tokens) is not int or max_output_tokens <= 0:
            raise ValueError("Analysis output budget must be positive")
        self.repository = repository
        self.provider = provider
        self.provider_name = provider_name
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.max_context_chars = max_context_chars
        self.max_output_tokens = max_output_tokens

    @staticmethod
    def _owner(owner_id: str) -> str:
        if not isinstance(owner_id, str) or not 1 <= len(owner_id.strip()) <= 128:
            raise ValueError("Owner must contain 1 to 128 characters")
        return owner_id.strip()

    async def create(
        self,
        document_id: UUID,
        owner_id: str,
        kind: AnalysisKind,
    ) -> AnalysisResponse:
        owner_id = self._owner(owner_id)
        if not isinstance(document_id, UUID) or kind not in ("cv", "jd"):
            raise ValueError("Invalid analysis input")
        try:
            source = await self.repository.load_input(document_id, owner_id)
        except (SQLAlchemyError, OSError) as exc:
            logger.warning("analysis_load_failed")
            raise AnalysisStorageError("Analysis storage unavailable") from exc
        if source is None:
            raise AnalysisNotFoundError("Document not found")
        if source.status != "completed":
            raise AnalysisNotReadyError("Document must be completed")
        if not source.chunks or not any(chunk.text.strip() for chunk in source.chunks):
            raise AnalysisNoContentError("Document has no usable text")
        if sum(len(chunk.text) for chunk in source.chunks) > self.max_context_chars:
            raise AnalysisTooLargeError("Document exceeds analysis context budget")
        context = ContextBuilder(max_chunks=len(source.chunks)).build(
            [RetrievedChunk(chunk, 0.0) for chunk in source.chunks]
        )
        messages = build_analysis_prompt(kind, context)
        if max(len(context.text), len(messages[1].content)) > self.max_context_chars:
            raise AnalysisTooLargeError("Document exceeds analysis context budget")
        if self.provider is None:
            raise ValueError("Analysis provider is not configured")
        try:
            async with asyncio.timeout(self.timeout_seconds):
                result = await self.provider.extract(messages, kind)
            profile = validate_profile(result, kind, context)
        except (TimeoutError, LLMTimeoutError) as exc:
            logger.warning("analysis_generation_failed kind=timeout")
            raise LLMTimeoutError("Analysis generation timed out") from exc
        except Exception as exc:
            logger.warning("analysis_generation_failed kind=provider")
            raise LLMProviderError("Analysis generation failed") from exc
        has_facts = any(getattr(profile, name) for name in type(profile).model_fields)
        status = "completed" if has_facts else "insufficient_evidence"
        provenance = AnalysisProvenance(
            schema_version=SCHEMA_VERSION,
            prompt_version=PROMPT_VERSION,
            provider=self.provider_name,
            model=self.model_name,
            timeout_seconds=self.timeout_seconds,
            max_output_tokens=self.max_output_tokens,
            max_context_chars=self.max_context_chars,
            messages=[AnalysisMessage(role=m.role, content=m.content) for m in messages],
        )
        try:
            saved = await self.repository.save(
                document_id=document_id,
                owner_id=owner_id,
                kind=kind,
                checksum=source.checksum,
                profile=profile,
                sources=[AnalysisSource.model_validate(s) for s in context.sources],
                provenance=provenance,
                status=status,
            )
        except AnalysisInputChangedError as exc:
            raise AnalysisNotReadyError("Document changed during analysis") from exc
        except (SQLAlchemyError, OSError) as exc:
            logger.warning("analysis_save_failed")
            raise AnalysisStorageError("Analysis storage unavailable") from exc
        logger.info(
            "analysis_created analysis_id=%s document_id=%s kind=%s version=%s status=%s",
            saved.id,
            document_id,
            kind,
            saved.version,
            status,
        )
        return saved

    async def get(self, analysis_id: UUID, owner_id: str) -> AnalysisResponse:
        owner_id = self._owner(owner_id)
        try:
            result = await self.repository.get(analysis_id, owner_id)
        except (SQLAlchemyError, OSError) as exc:
            raise AnalysisStorageError("Analysis storage unavailable") from exc
        if result is None:
            raise AnalysisNotFoundError("Analysis not found")
        return result

    async def list(
        self,
        document_id: UUID,
        owner_id: str,
        kind: AnalysisKind | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[AnalysisSummary]:
        owner_id = self._owner(owner_id)
        if (
            kind not in (None, "cv", "jd")
            or type(limit) is not int
            or not 1 <= limit <= 100
            or type(offset) is not int
            or offset < 0
        ):
            raise ValueError("Invalid analysis list parameters")
        try:
            result = await self.repository.list(document_id, owner_id, kind, limit, offset)
        except (SQLAlchemyError, OSError) as exc:
            raise AnalysisStorageError("Analysis storage unavailable") from exc
        if result is None:
            raise AnalysisNotFoundError("Document not found")
        return result
