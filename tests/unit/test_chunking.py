import pytest

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
    assert [text[chunk.char_start : chunk.char_end] for chunk in first] == [
        chunk.text for chunk in first
    ]
    assert [chunk.index for chunk in first] == list(range(len(first)))
    assert all(chunk.char_start < chunk.char_end for chunk in first)
    assert all(len(chunk.text) <= chunker.chunk_size for chunk in first)


def test_chunking_empty_text_returns_no_chunks() -> None:
    assert DeterministicTextChunker().split(" \n\t ") == []


def test_chunking_preserves_normalized_structure_and_source_offsets() -> None:
    text = "Heading\n\nParagraph one.\n\nParagraph two."

    chunks = DeterministicTextChunker(chunk_size=100, chunk_overlap=10).split(text)

    assert chunks[0].text == text
    assert chunks[0].char_start == 0
    assert chunks[0].char_end == len(text)


def test_chunking_makes_forward_progress_for_high_valid_overlap() -> None:
    chunker = DeterministicTextChunker(chunk_size=5, chunk_overlap=4)

    chunks = chunker.split("abcdefghijk")

    assert [chunk.text for chunk in chunks] == [
        "abcde",
        "bcdef",
        "cdefg",
        "defgh",
        "efghi",
        "fghij",
        "ghijk",
    ]
    assert all(
        current.char_end > previous.char_end
        for previous, current in zip(chunks, chunks[1:], strict=False)
    )


@pytest.mark.parametrize(
    ("chunk_size", "chunk_overlap"),
    [
        (0, 0),
        (10, -1),
        (10, 10),
        (10, 11),
    ],
)
def test_chunking_rejects_invalid_configuration(chunk_size: int, chunk_overlap: int) -> None:
    with pytest.raises(ValueError):
        DeterministicTextChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
