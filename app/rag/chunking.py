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
        if not text.strip():
            return []

        chunks: list[TextChunk] = []
        text_length = len(text)
        start = self._skip_whitespace(text, 0, text_length)
        content_end = text_length
        while content_end > start and text[content_end - 1].isspace():
            content_end -= 1

        while start < content_end:
            end = min(start + self.chunk_size, content_end)
            if end < content_end:
                boundary = self._find_last_whitespace(text, start, end)
                if boundary is not None:
                    end = boundary

            while end > start and text[end - 1].isspace():
                end -= 1

            chunks.append(
                TextChunk(
                    index=len(chunks),
                    text=text[start:end],
                    char_start=start,
                    char_end=end,
                )
            )

            if end >= content_end:
                break

            next_start = max(end - self.chunk_overlap, start + 1)
            next_boundary = self._find_first_whitespace(text, next_start, end)
            start = (
                self._skip_whitespace(text, next_boundary, content_end)
                if next_boundary is not None
                else next_start
            )

        return chunks

    @staticmethod
    def _skip_whitespace(text: str, start: int, end: int) -> int:
        while start < end and text[start].isspace():
            start += 1
        return start

    @staticmethod
    def _find_last_whitespace(text: str, start: int, end: int) -> int | None:
        for index in range(end - 1, start, -1):
            if text[index].isspace():
                return index
        return None

    @staticmethod
    def _find_first_whitespace(text: str, start: int, end: int) -> int | None:
        for index in range(start, end):
            if text[index].isspace():
                return index
        return None
