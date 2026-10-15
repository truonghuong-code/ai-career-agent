from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.integrations.llm.analysis import (
    FakeAnalysisProvider,
    OpenAIAnalysisProvider,
    create_analysis_provider,
)
from app.integrations.llm.provider import LLMProviderError, LLMTimeoutError
from app.rag.prompt import PromptMessage
from app.schemas.analysis import CVProfile, JDProfile


@pytest.mark.parametrize("kind,model", [("cv", CVProfile), ("jd", JDProfile)])
async def test_p4_t08_openai_domain_schema(kind, model):
    profile = model.model_validate({field: [] for field in model.model_fields})
    messages = (PromptMessage("system", "Extract"), PromptMessage("user", "source text"))
    client = AsyncMock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content=profile.model_dump_json(), refusal=None),
            )
        ]
    )
    settings = Settings(
        _env_file=None,
        llm_provider="openai",
        openai_api_key="test-only",
        analysis_max_output_tokens=2048,
    )
    with patch("app.integrations.llm.provider.AsyncOpenAI", return_value=client):
        provider = create_analysis_provider(settings)
        assert isinstance(provider, OpenAIAnalysisProvider)
        assert await provider.extract(messages, kind) == profile
    request = client.chat.completions.create.call_args.kwargs
    assert request["response_format"]["json_schema"]["schema"] == model.model_json_schema()
    assert request["max_completion_tokens"] == 2048
    client.close.assert_awaited_once()


@pytest.mark.parametrize(
    "payload,finish,refusal",
    [
        ("{}", "stop", None),
        ("", "stop", None),
        ("not JSON", "stop", None),
        ("{}", "length", None),
        ("{}", "stop", "refused"),
    ],
)
async def test_p4_t08_invalid_structured_output(payload, finish, refusal):
    client = AsyncMock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason=finish,
                message=SimpleNamespace(content=payload, refusal=refusal),
            )
        ]
    )
    with patch("app.integrations.llm.provider.AsyncOpenAI", return_value=client):
        provider = create_analysis_provider(
            Settings(_env_file=None, llm_provider="openai", openai_api_key="test-only")
        )
        with pytest.raises(LLMProviderError):
            await provider.extract((), "cv")
    client.close.assert_awaited_once()


@pytest.mark.parametrize("error", [LLMProviderError("safe"), LLMTimeoutError("timeout")])
async def test_p4_t08_transport_errors(error):
    provider = OpenAIAnalysisProvider(
        SimpleNamespace(generate_structured=AsyncMock(side_effect=error))
    )
    with pytest.raises(type(error)):
        await provider.extract((), "cv")


@pytest.mark.parametrize(
    "values",
    [
        {"llm_provider": "bad"},
        {"llm_provider": "openai", "openai_api_key": None},
        {"llm_provider": "openai", "openai_api_key": " "},
    ],
)
def test_p4_t14_bad_provider_config(values):
    with pytest.raises(ValueError):
        create_analysis_provider(Settings(_env_file=None, **values))


def test_p4_t08_default_is_fake_and_settings_are_prefixed(monkeypatch):
    monkeypatch.setenv("AI_CAREER_AGENT_ANALYSIS_MAX_CONTEXT_CHARS", "1234")
    monkeypatch.setenv("AI_CAREER_AGENT_ANALYSIS_MAX_OUTPUT_TOKENS", "321")
    settings = Settings(_env_file=None, llm_provider="fake")
    assert settings.analysis_max_context_chars == 1234
    assert settings.analysis_max_output_tokens == 321
    assert isinstance(create_analysis_provider(settings), FakeAnalysisProvider)


@pytest.mark.parametrize("field", ["analysis_max_context_chars", "analysis_max_output_tokens"])
def test_p4_t06_invalid_limits(field):
    with pytest.raises(ValueError):
        Settings(_env_file=None, **{field: 0})
