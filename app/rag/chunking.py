import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    index: int
    text: str
    char_start: int
    char_end: int


class DeterministicTextChunker:
    """Split normalized text into stable, overlapping chunks without model dependencies."""

    def __init__(self, chunk_size: int = 1_000, chunk_overlap: int = 150) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be greater than zero")
        if not 0 <= chunk_overlap < chunk_size:
            raise ValueError("chunk_overlap must be non-negative and smaller than chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split(self, text: str) -> list[TextChunk]:
        normalized = re.sub(r"\s+", " ", text).strip()
        if not normalized:
            return []

        chunks: list[TextChunk] = []
        start = 0
        text_length = len(normalized)

        while start < text_length:
            end = min(start + self.chunk_size, text_length)
            if end < text_length:
                boundary = normalized.rfind(" ", start, end + 1)
                if boundary > start:
                    end = boundary

            chunk_text = normalized[start:end].strip()
            if chunk_text:
                raw_chunk = normalized[start:end]
                char_start = start + (len(raw_chunk) - len(raw_chunk.lstrip()))
                char_end = char_start + len(chunk_text)
                chunks.append(
                    TextChunk(
                        index=len(chunks),
                        text=chunk_text,
                        char_start=char_start,
                        char_end=char_end,
                    )
                )

            if end >= text_length:
                break

            next_start = max(end - self.chunk_overlap, start + 1)
            next_boundary = normalized.find(" ", next_start, end)
            start = next_boundary + 1 if next_boundary != -1 else next_start

        return chunks
