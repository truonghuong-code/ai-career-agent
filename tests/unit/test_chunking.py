from app.rag.chunking import DeterministicTextChunker


def test_chunking_is_deterministic_and_preserves_overlap() -> None:
    chunker = DeterministicTextChunker(chunk_size=24, chunk_overlap=8)
    text = "Alpha beta gamma delta epsilon zeta eta theta iota kappa."

    first = chunker.split(text)
    second = chunker.split(text)

    assert first == second
    assert [chunk.text for chunk in first] == [
        "Alpha beta gamma delta",
        "delta epsilon zeta eta",
        "eta theta iota kappa.",
    ]
    assert all(chunk.char_start < chunk.char_end for chunk in first)


def test_chunking_empty_text_returns_no_chunks() -> None:
    assert DeterministicTextChunker().split(" \n\t ") == []
