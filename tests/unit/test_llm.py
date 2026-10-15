from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from openai import APITimeoutError

from app.core.config import Settings
from app.integrations.llm.provider import (
    FakeLLMProvider,
    LLMProviderError,
    LLMResponse,
    LLMTimeoutError,
    OpenAILLMProvider,
    create_llm_provider,
)
from app.rag.prompt import PromptMessage

MESSAGES = (PromptMessage("system", "Grounded answer"), PromptMessage("user", "Context"))


async def test_fake_is_deterministic():
    provider = FakeLLMProvider()
    assert await provider.generate(MESSAGES) == await provider.generate(MESSAGES)
    assert (await provider.generate(MESSAGES)).insufficient_evidence
    response = LLMResponse("Python [Source 1]", (1,), False)
    assert await FakeLLMProvider(response).generate(MESSAGES) == response


@pytest.mark.parametrize(
    "settings",
    [
        {"llm_provider": "unknown"},
        {"llm_provider": "openai", "openai_api_key": None},
        {"llm_provider": "openai", "openai_api_key": "  "},
    ],
)
def test_invalid_provider_configuration(settings):
    with pytest.raises(ValueError):
        create_llm_provider(Settings(_env_file=None, **settings))


@pytest.mark.parametrize(
    "field,value",
    [
        ("llm_timeout_seconds", 0),
        ("llm_timeout_seconds", float("nan")),
        ("llm_max_output_tokens", 0),
        ("qa_max_context_chunks", 0),
        ("llm_model", " "),
    ],
)
def test_invalid_settings(field, value):
    with pytest.raises(ValueError):
        Settings(_env_file=None, **{field: value})


@pytest.mark.parametrize(
    "content,reason,refusal,expected",
    [
        (
            '{"answer":"Python [Source 1]","source_numbers":[1],"insufficient_evidence":false}',
            "stop",
            None,
            None,
        ),
        ("", "stop", None, LLMProviderError),
        ("not json", "stop", None, LLMProviderError),
        ("{}", "stop", None, LLMProviderError),
        (
            '{"answer":" ","source_numbers":[],"insufficient_evidence":false}',
            "stop",
            None,
            LLMProviderError,
        ),
        ("{}", "length", None, LLMProviderError),
        ("{}", "stop", "refused", LLMProviderError),
    ],
)
async def test_openai_response_contract(content, reason, refusal, expected):
    client = AsyncMock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason=reason, message=SimpleNamespace(content=content, refusal=refusal)
            )
        ]
    )
    with patch("app.integrations.llm.provider.AsyncOpenAI", return_value=client) as factory:
        provider = OpenAILLMProvider("test-key", "test-model", 2, 100)
        if expected:
            with pytest.raises(expected):
                await provider.generate(MESSAGES)
        else:
            assert await provider.generate(MESSAGES) == LLMResponse(
                "Python [Source 1]", (1,), False
            )
        factory.assert_called_once_with(api_key="test-key", timeout=2, max_retries=0)
    client.close.assert_awaited_once()
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["messages"] == [{"role": m.role, "content": m.content} for m in MESSAGES]
    assert kwargs["max_completion_tokens"] == 100
    assert kwargs["response_format"]["json_schema"]["strict"] is True


@pytest.mark.parametrize(
    "error,expected",
    [
        (RuntimeError("secret-provider-body"), LLMProviderError),
        (APITimeoutError(request=httpx.Request("POST", "https://example.test")), LLMTimeoutError),
    ],
)
async def test_openai_errors_are_safe(error, expected):
    client = AsyncMock()
    client.chat.completions.create.side_effect = error
    with patch("app.integrations.llm.provider.AsyncOpenAI", return_value=client):
        with pytest.raises(expected) as caught:
            await OpenAILLMProvider("test-key", "test-model", 2, 100).generate(MESSAGES)
    assert "secret" not in str(caught.value)
    client.close.assert_awaited_once()


def test_factory_selection_and_environment(monkeypatch):
    monkeypatch.setenv("AI_CAREER_AGENT_LLM_PROVIDER", "fake")
    monkeypatch.setenv("AI_CAREER_AGENT_QA_MAX_CONTEXT_CHUNKS", "3")
    settings = Settings(_env_file=None)
    assert settings.qa_max_context_chunks == 3
    assert isinstance(create_llm_provider(settings), FakeLLMProvider)
    settings = Settings(_env_file=None, llm_provider="openai", openai_api_key="test-secret")
    assert isinstance(create_llm_provider(settings), OpenAILLMProvider)
    assert "test-secret" not in repr(settings)


async def test_openai_missing_choices():
    client = AsyncMock()
    client.chat.completions.create.return_value = SimpleNamespace(choices=[])
    with patch("app.integrations.llm.provider.AsyncOpenAI", return_value=client):
        with pytest.raises(LLMProviderError):
            await OpenAILLMProvider("test-key", "test-model", 2, 100).generate(MESSAGES)
    client.close.assert_awaited_once()
