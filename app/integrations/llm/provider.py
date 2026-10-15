from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from openai import APITimeoutError, AsyncOpenAI
from pydantic import BaseModel, ConfigDict, field_validator

from app.core.config import Settings
from app.rag.prompt import PromptMessage

INSUFFICIENT_EVIDENCE = (
    "The provided documents do not contain enough evidence to answer this question."
)


class LLMProviderError(RuntimeError):
    """Safe application error; provider details must not reach clients or logs."""


class LLMTimeoutError(LLMProviderError):
    """The generation deadline was exceeded."""


@dataclass(frozen=True)
class LLMResponse:
    answer: str
    source_numbers: tuple[int, ...]
    insufficient_evidence: bool


class LLMProvider(Protocol):
    async def generate(self, messages: Sequence[PromptMessage]) -> LLMResponse: ...


class FakeLLMProvider:
    """Offline stub, deliberately makes no claims about semantic evidence."""

    def __init__(self, response: LLMResponse | None = None) -> None:
        self.response = response or LLMResponse(INSUFFICIENT_EVIDENCE, (), True)

    async def generate(self, messages: Sequence[PromptMessage]) -> LLMResponse:
        return self.response


class _AnswerPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    answer: str
    source_numbers: list[int]
    insufficient_evidence: bool

    @field_validator("answer")
    @classmethod
    def nonempty_answer(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Empty answer")
        return value.strip()


class OpenAILLMProvider:
    def __init__(
        self, api_key: str, model: str, timeout_seconds: float, max_output_tokens: int
    ) -> None:
        self._api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens

    async def generate(self, messages: Sequence[PromptMessage]) -> LLMResponse:
        client = AsyncOpenAI(api_key=self._api_key, timeout=self.timeout_seconds, max_retries=0)
        try:
            response = await client.chat.completions.create(
                model=self.model,
                messages=[{"role": m.role, "content": m.content} for m in messages],
                max_completion_tokens=self.max_output_tokens,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "grounded_answer",
                        "strict": True,
                        "schema": _AnswerPayload.model_json_schema(),
                    },
                },
            )
            if not response.choices:
                raise LLMProviderError("LLM returned an invalid response")
            choice = response.choices[0]
            if choice.finish_reason != "stop" or choice.message.refusal:
                raise LLMProviderError("LLM returned an incomplete response")
            payload = _AnswerPayload.model_validate_json(choice.message.content or "")
            return LLMResponse(
                payload.answer, tuple(payload.source_numbers), payload.insufficient_evidence
            )
        except APITimeoutError as exc:
            raise LLMTimeoutError("LLM request timed out") from exc
        except LLMProviderError:
            raise
        except Exception as exc:
            raise LLMProviderError("LLM request failed") from exc
        finally:
            await client.close()


def create_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "fake":
        return FakeLLMProvider()
    if settings.llm_provider == "openai":
        if not settings.openai_api_key or not settings.openai_api_key.strip():
            raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        return OpenAILLMProvider(
            settings.openai_api_key,
            settings.llm_model,
            settings.llm_timeout_seconds,
            settings.llm_max_output_tokens,
        )
    raise ValueError("Unsupported LLM provider")
