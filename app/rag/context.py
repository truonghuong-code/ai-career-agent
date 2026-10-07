from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from app.db.repositories.documents import RetrievedChunk


@dataclass(frozen=True)
class ContextSource:
    number: int
    document_id: UUID
    chunk_id: UUID
    chunk_index: int
    text: str


@dataclass(frozen=True)
class BuiltContext:
    text: str
    sources: tuple[ContextSource, ...]


class ContextBuilder:
    def __init__(self, max_chunks: int = 5) -> None:
        if max_chunks <= 0:
            raise ValueError("max_chunks must be greater than 0")

        self.max_chunks = max_chunks

    def build(
        self,
        results: Sequence[RetrievedChunk],
    ) -> BuiltContext:
        if not results:
            return BuiltContext(text="", sources=())

        selected_results = results[: self.max_chunks]

        sections = []
        sources = []

        for number, result in enumerate(selected_results, start=1):
            sections.append(
                f"[Source {number}]\n"
                f"{result.chunk.text}"
            )

            sources.append(
                ContextSource(
                    number=number,
                    document_id=result.chunk.document_id,
                    chunk_id=result.chunk.id,
                    chunk_index=result.chunk.chunk_index,
                    text=result.chunk.text,
                )
            )

        return BuiltContext(
            text="\n\n".join(sections),
            sources=tuple(sources),
        )