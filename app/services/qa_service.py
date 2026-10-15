import asyncio
import logging
import math
import re
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from app.integrations.llm.provider import (
    INSUFFICIENT_EVIDENCE,
    LLMProvider,
    LLMProviderError,
    LLMResponse,
    LLMTimeoutError,
)
from app.rag.context import ContextBuilder, ContextSource
from app.rag.embeddings import EmbeddingProviderError
from app.rag.prompt import PromptBuilder
from app.services.document_service import DocumentSearchService

logger = logging.getLogger(__name__)


class QARetrievalError(RuntimeError):
    """Retrieval failed rather than returning an empty result."""


class QAEmbeddingError(QARetrievalError):
    """The retrieval embedding provider failed."""


@dataclass(frozen=True)
class GroundedAnswer:
    answer: str
    status: Literal["answered", "no_context", "insufficient_evidence"]
    sources: tuple[ContextSource, ...]


class GroundedQAService:
    def __init__(
        self,
        search_service: DocumentSearchService,
        llm_provider: LLMProvider,
        context_builder: ContextBuilder | None = None,
        prompt_builder: PromptBuilder | None = None,
        timeout_seconds: float = 30,
    ) -> None:
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive and finite")
        self.search_service = search_service
        self.llm_provider = llm_provider
        self.context_builder = context_builder or ContextBuilder()
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.timeout_seconds = timeout_seconds

    async def answer(
        self,
        *,
        owner_id: str,
        question: str,
        limit: int = 5,
        document_ids: list[UUID] | None = None,
    ) -> GroundedAnswer:
        if not isinstance(owner_id, str) or not owner_id.strip():
            raise ValueError("owner_id is required")
        if not isinstance(question, str) or not 1 <= len(question.strip()) <= 5000:
            raise ValueError("question must contain 1 to 5000 characters")
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("limit must be between 1 and 20")
        if document_ids is not None and (
            not isinstance(document_ids, list)
            or any(not isinstance(value, UUID) for value in document_ids)
        ):
            raise ValueError("document_ids must be a list of UUIDs")
        try:
            results = await self.search_service.search(
                owner_id=owner_id.strip(),
                query=question.strip(),
                limit=limit,
                document_ids=document_ids,
            )
        except EmbeddingProviderError as exc:
            logger.warning("qa_retrieval_failed kind=embedding")
            raise QAEmbeddingError("Question retrieval failed") from exc
        except Exception as exc:
            logger.warning("qa_retrieval_failed kind=infrastructure")
            raise QARetrievalError("Question retrieval failed") from exc
        context = self.context_builder.build(results)
        if not context.sources or not any(source.text.strip() for source in context.sources):
            logger.info("qa_completed status=no_context sources=0")
            return GroundedAnswer(INSUFFICIENT_EVIDENCE, "no_context", ())
        messages = self.prompt_builder.build(question, context)
        try:
            async with asyncio.timeout(self.timeout_seconds):
                response = await self.llm_provider.generate(messages)
            self._validate_response(response, {s.number for s in context.sources})
        except (TimeoutError, LLMTimeoutError) as exc:
            logger.warning("qa_generation_failed kind=timeout")
            raise LLMTimeoutError("LLM request timed out") from exc
        except Exception as exc:
            logger.warning("qa_generation_failed kind=provider")
            raise LLMProviderError("Answer generation failed") from exc
        if response.insufficient_evidence:
            logger.info("qa_completed status=insufficient_evidence sources=0")
            return GroundedAnswer(INSUFFICIENT_EVIDENCE, "insufficient_evidence", ())
        sources = tuple(s for s in context.sources if s.number in response.source_numbers)
        logger.info("qa_completed status=answered sources=%s", len(sources))
        return GroundedAnswer(response.answer.strip(), "answered", sources)

    @staticmethod
    def _validate_response(response: LLMResponse, available: set[int]) -> None:
        if (
            not isinstance(response, LLMResponse)
            or not isinstance(response.answer, str)
            or not response.answer.strip()
            or type(response.insufficient_evidence) is not bool
            or not isinstance(response.source_numbers, tuple)
            or any(type(n) is not int or n <= 0 for n in response.source_numbers)
        ):
            raise LLMProviderError("Invalid LLM response")
        numbers = set(response.source_numbers)
        markers = {int(n) for n in re.findall(r"\[Source (\d+)\]", response.answer)}
        if response.insufficient_evidence:
            if numbers or markers:
                raise LLMProviderError("Invalid insufficient-evidence citations")
        elif not numbers or not numbers <= available or markers != numbers:
            raise LLMProviderError("Invalid LLM citations")
