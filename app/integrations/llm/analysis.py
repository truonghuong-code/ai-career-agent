from collections.abc import Sequence
from typing import Protocol

from app.core.config import Settings
from app.integrations.llm.provider import OpenAILLMProvider
from app.rag.prompt import PromptMessage
from app.schemas.analysis import AnalysisKind, CVProfile, JDProfile


class AnalysisProvider(Protocol):
    async def extract(
        self, messages: Sequence[PromptMessage], kind: AnalysisKind
    ) -> CVProfile | JDProfile: ...


class FakeAnalysisProvider:
    """Offline conservative stub; controlled profiles may be supplied by tests."""

    def __init__(self, profile: CVProfile | JDProfile | None = None) -> None:
        self.profile = profile

    async def extract(
        self, messages: Sequence[PromptMessage], kind: AnalysisKind
    ) -> CVProfile | JDProfile:
        if self.profile is not None:
            return self.profile.model_copy(deep=True)
        model = CVProfile if kind == "cv" else JDProfile
        return model.model_validate({name: [] for name in model.model_fields})


class OpenAIAnalysisProvider:
    def __init__(self, transport: OpenAILLMProvider) -> None:
        self.transport = transport

    async def extract(
        self, messages: Sequence[PromptMessage], kind: AnalysisKind
    ) -> CVProfile | JDProfile:
        model = CVProfile if kind == "cv" else JDProfile
        return await self.transport.generate_structured(messages, model)


def create_analysis_provider(settings: Settings) -> AnalysisProvider:
    if settings.llm_provider == "fake":
        return FakeAnalysisProvider()
    if settings.llm_provider == "openai":
        if not settings.openai_api_key or not settings.openai_api_key.strip():
            raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        return OpenAIAnalysisProvider(
            OpenAILLMProvider(
                settings.openai_api_key,
                settings.llm_model,
                settings.llm_timeout_seconds,
                settings.analysis_max_output_tokens,
            )
        )
    raise ValueError("Unsupported analysis provider")
