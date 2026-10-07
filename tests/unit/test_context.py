from uuid import UUID

import pytest

from app.db.models.document import DocumentChunk
from app.db.repositories.documents import RetrievedChunk
from app.rag.context import ContextBuilder

DOCUMENT_ID_A = UUID("11111111-1111-1111-1111-111111111111")
DOCUMENT_ID_B = UUID("22222222-2222-2222-2222-222222222222")
DOCUMENT_ID_C = UUID("33333333-3333-3333-3333-333333333333")

CHUNK_ID_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
CHUNK_ID_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
CHUNK_ID_C = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


def make_result(
    *,
    text: str,
    document_id: UUID = DOCUMENT_ID_A,
    chunk_id: UUID = CHUNK_ID_A,
    chunk_index: int = 0,
    score: float = 0.9,
) -> RetrievedChunk:
    chunk = DocumentChunk(
        id=chunk_id,
        document_id=document_id,
        owner_id="test-user",
        chunk_index=chunk_index,
        text=text,
        char_start=0,
        char_end=len(text),
    )

    return RetrievedChunk(
        chunk=chunk,
        score=score,
    )


# CB-TC-01
def test_build_returns_empty_context_for_empty_results():
    # Given
    builder = ContextBuilder(max_chunks=5)

    # When
    result = builder.build([])

    # Then
    assert result.text == ""
    assert result.sources == ()


# CB-TC-02
def test_build_respects_max_chunks():
    # Given
    builder = ContextBuilder(max_chunks=2)

    results = [
        make_result(
            text="A",
            document_id=DOCUMENT_ID_A,
            chunk_id=CHUNK_ID_A,
        ),
        make_result(
            text="B",
            document_id=DOCUMENT_ID_B,
            chunk_id=CHUNK_ID_B,
        ),
        make_result(
            text="C",
            document_id=DOCUMENT_ID_C,
            chunk_id=CHUNK_ID_C,
        ),
    ]

    # When
    result = builder.build(results)

    # Then
    assert len(result.sources) == 2
    assert result.sources[0].text == "A"
    assert result.sources[1].text == "B"
    assert "C" not in result.text


# CB-TC-03
def test_build_preserves_retrieval_order():
    # Given
    builder = ContextBuilder(max_chunks=5)

    results = [
        make_result(
            text="C",
            document_id=DOCUMENT_ID_C,
            chunk_id=CHUNK_ID_C,
        ),
        make_result(
            text="A",
            document_id=DOCUMENT_ID_A,
            chunk_id=CHUNK_ID_A,
        ),
        make_result(
            text="B",
            document_id=DOCUMENT_ID_B,
            chunk_id=CHUNK_ID_B,
        ),
    ]

    # When
    result = builder.build(results)

    # Then
    assert [source.text for source in result.sources] == [
        "C",
        "A",
        "B",
    ]


# CB-TC-04
def test_build_numbers_sources_starting_from_one():
    # Given
    builder = ContextBuilder(max_chunks=5)

    results = [
        make_result(
            text="A",
            document_id=DOCUMENT_ID_A,
            chunk_id=CHUNK_ID_A,
        ),
        make_result(
            text="B",
            document_id=DOCUMENT_ID_B,
            chunk_id=CHUNK_ID_B,
        ),
        make_result(
            text="C",
            document_id=DOCUMENT_ID_C,
            chunk_id=CHUNK_ID_C,
        ),
    ]

    # When
    result = builder.build(results)

    # Then
    assert [source.number for source in result.sources] == [1, 2, 3]


# CB-TC-05
def test_build_formats_context():
    # Given
    builder = ContextBuilder(max_chunks=5)

    results = [
        make_result(
            text="Python experience",
            document_id=DOCUMENT_ID_A,
            chunk_id=CHUNK_ID_A,
        ),
        make_result(
            text="FastAPI experience",
            document_id=DOCUMENT_ID_B,
            chunk_id=CHUNK_ID_B,
        ),
    ]

    # When
    result = builder.build(results)

    # Then
    assert result.text == (
        "[Source 1]\n"
        "Python experience\n\n"
        "[Source 2]\n"
        "FastAPI experience"
    )


# CB-TC-06
def test_build_maps_source_to_original_chunk():
    # Given
    builder = ContextBuilder(max_chunks=5)

    result_a = make_result(
        text="Python experience",
        document_id=DOCUMENT_ID_A,
        chunk_id=CHUNK_ID_A,
        chunk_index=4,
    )

    # When
    result = builder.build([result_a])

    # Then
    source = result.sources[0]

    assert source.number == 1
    assert source.document_id == DOCUMENT_ID_A
    assert source.chunk_id == CHUNK_ID_A
    assert source.chunk_index == 4
    assert source.text == "Python experience"


# CB-TC-07
def test_build_is_deterministic():
    # Given
    builder = ContextBuilder(max_chunks=5)

    results = [
        make_result(
            text="Python experience",
            document_id=DOCUMENT_ID_A,
            chunk_id=CHUNK_ID_A,
            chunk_index=0,
        ),
        make_result(
            text="FastAPI experience",
            document_id=DOCUMENT_ID_B,
            chunk_id=CHUNK_ID_B,
            chunk_index=1,
        ),
    ]

    # When
    first = builder.build(results)
    second = builder.build(results)

    # Then
    assert first == second


# CB-TC-08 + CB-TC-09
@pytest.mark.parametrize("max_chunks", [0, -1])
def test_rejects_non_positive_max_chunks(max_chunks: int):
    # When / Then
    with pytest.raises(ValueError):
        ContextBuilder(max_chunks=max_chunks)


# CB-TC-10
def test_build_includes_all_results_when_fewer_than_max_chunks():
    # Given
    builder = ContextBuilder(max_chunks=5)

    results = [
        make_result(
            text="A",
            document_id=DOCUMENT_ID_A,
            chunk_id=CHUNK_ID_A,
        ),
        make_result(
            text="B",
            document_id=DOCUMENT_ID_B,
            chunk_id=CHUNK_ID_B,
        ),
    ]

    # When
    result = builder.build(results)

    # Then
    assert len(result.sources) == 2
    assert [source.text for source in result.sources] == ["A", "B"]

    assert result.text == (
        "[Source 1]\n"
        "A\n\n"
        "[Source 2]\n"
        "B"
    )