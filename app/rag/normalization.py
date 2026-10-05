import re


class TextNormalizer:
    """Conservatively normalize parser output before deterministic chunking."""

    def normalize(self, text: str) -> str:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        return re.sub(r"\n{3,}", "\n\n", normalized)
