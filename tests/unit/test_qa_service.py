import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.db.repositories.documents import RetrievedChunk
from app.integrations.llm.provider import (
    INSUFFICIENT_EVIDENCE,
    FakeLLMProvider,
    LLMProviderError,
    LLMResponse,
    LLMTimeoutError,
)
from app.rag.context import ContextBuilder
from app.rag.embeddings import EmbeddingProviderError
from app.services.qa_service import GroundedQAService, QAEmbeddingError, QARetrievalError


def matches(count=3):
    return [
        RetrievedChunk(
            SimpleNamespace(
                id=uuid4(),
                document_id=uuid4(),
                chunk_index=i,
                text=f"Python fact {i}",
            ),
            1 - i / 10,
        )
        for i in range(count)
    ]


async def test_pipeline_preserves_order_context_cap_and_filters():
    rows = matches()
    search = SimpleNamespace(search=AsyncMock(return_value=rows))
    provider = SimpleNamespace(
        generate=AsyncMock(
            return_value=LLMResponse(
                "Facts [Source 2] [Source 1]",
                (2, 1, 2),
                False,
            )
        )
    )
    service = GroundedQAService(search, provider, ContextBuilder(2))
    ids = [rows[0].chunk.document_id]
    result = await service.answer(
        owner_id=" owner ", question=" Python? ", limit=3, document_ids=ids
    )
    search.search.assert_awaited_once_with(
        owner_id="owner", query="Python?", limit=3, document_ids=ids
    )
    assert result.status == "answered"
    assert [s.chunk_id for s in result.sources] == [r.chunk.id for r in rows[:2]]
    assert [s.number for s in result.sources] == [1, 2]
    prompt = provider.generate.call_args.args[0]
    assert rows[2].chunk.text not in prompt[1].content
    assert prompt[1].content.endswith("Question:\nPython?")


async def test_cited_subset_keeps_original_numbers():
    service = GroundedQAService(
        SimpleNamespace(search=AsyncMock(return_value=matches())),
        FakeLLMProvider(LLMResponse("Fact [Source 3]", (3,), False)),
    )
    result = await service.answer(owner_id="owner", question="Python?")
    assert [s.number for s in result.sources] == [3]


@pytest.mark.parametrize(
    "changes",
    [
        {"question": ""},
        {"question": "  "},
        {"question": None},
        {"question": "a" * 5001},
        {"owner_id": " "},
        {"limit": 0},
        {"limit": 21},
        {"limit": True},
        {"document_ids": ["bad"]},
    ],
)
async def test_invalid_input_never_retrieves(changes):
    search = SimpleNamespace(search=AsyncMock())
    service = GroundedQAService(search, FakeLLMProvider())
    with pytest.raises(ValueError):
        await service.answer(**({"owner_id": "owner", "question": "Python?"} | changes))
    search.search.assert_not_awaited()


async def test_no_context_skips_llm():
    llm = SimpleNamespace(generate=AsyncMock())
    result = await GroundedQAService(
        SimpleNamespace(search=AsyncMock(return_value=[])), llm
    ).answer(
        owner_id="owner",
        question="Python?",
        document_ids=[],
    )
    assert result.status == "no_context"
    assert result.sources == ()
    llm.generate.assert_not_awaited()


async def test_insufficient_evidence_uses_safe_canonical_answer():
    service = GroundedQAService(
        SimpleNamespace(search=AsyncMock(return_value=matches())),
        FakeLLMProvider(LLMResponse("Unsupported model prose", (), True)),
    )
    result = await service.answer(owner_id="owner", question="Python?")
    assert result.status == "insufficient_evidence"
    assert result.answer == INSUFFICIENT_EVIDENCE
    assert result.sources == ()


@pytest.mark.parametrize(
    "response",
    [
        LLMResponse("Invented [Source 99]", (99,), False),
        LLMResponse("Missing citations", (), False),
        LLMResponse("Mismatch [Source 2]", (1,), False),
        LLMResponse("", (1,), False),
        LLMResponse("Bad type [Source 1]", (True,), False),
        LLMResponse("Contradiction [Source 1]", (1,), True),
        None,
    ],
)
async def test_invalid_response_is_provider_failure(response):
    provider = SimpleNamespace(generate=AsyncMock(return_value=response))
    service = GroundedQAService(SimpleNamespace(search=AsyncMock(return_value=matches())), provider)
    with pytest.raises(LLMProviderError):
        await service.answer(owner_id="owner", question="Python?")


@pytest.mark.parametrize(
    "error,expected",
    [
        (RuntimeError("secret DB credentials"), QARetrievalError),
        (EmbeddingProviderError("secret API key"), QAEmbeddingError),
    ],
)
async def test_retrieval_failure_is_not_empty_context(error, expected, caplog):
    provider = SimpleNamespace(generate=AsyncMock())
    service = GroundedQAService(SimpleNamespace(search=AsyncMock(side_effect=error)), provider)
    with pytest.raises(expected):
        await service.answer(owner_id="owner", question="private question")
    provider.generate.assert_not_awaited()
    assert "secret" not in caplog.text
    assert "private question" not in caplog.text


async def test_provider_deadline_cancels_pending_generation():
    cancelled = False

    async def delayed(messages):
        nonlocal cancelled
        try:
            await asyncio.sleep(10)
        finally:
            cancelled = True

    service = GroundedQAService(
        SimpleNamespace(search=AsyncMock(return_value=matches())),
        SimpleNamespace(generate=delayed),
        timeout_seconds=0.001,
    )
    with pytest.raises(LLMTimeoutError):
        await service.answer(owner_id="owner", question="Python?")
    assert cancelled
