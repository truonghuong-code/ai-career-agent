# Phase 3.1 — Context Builder Test Design

## 1. Test Objective

The purpose of these tests is to verify that `ContextBuilder` converts ordered retrieval results into deterministic LLM context while preserving the source information required for later citation and traceability.

The tests verify the following behavior:

- empty retrieval handling
- maximum chunk selection
- retrieval-order preservation
- sequential source numbering
- deterministic context formatting
- correct source-to-chunk mapping
- deterministic output
- invalid `max_chunks` configuration

The tests do not verify retrieval quality, embedding generation, database queries, prompt construction, or LLM behavior.

---

## 2. Test Scope

### In Scope

The following components are tested:

```text id="3akpjc"
ContextBuilder
ContextSource
BuiltContext
```

Primary interface under test:

```text id="p3tcvz"
ContextBuilder.build(
    results: Sequence[RetrievedChunk]
) -> BuiltContext
```

### Out of Scope

The following components are outside the scope of Phase 3.1 tests:

```text id="ofnbb4"
DocumentRepository
PostgreSQL / pgvector
EmbeddingProvider
DocumentSearchService retrieval behavior
PromptBuilder
LLMProvider
HTTP API
```

Retrieval behavior itself is already covered by Phase 2 tests.

---

## 3. Test Level

`ContextBuilder` is deterministic application/RAG logic with no database, network, embedding, or LLM dependency.

Therefore, Phase 3.1 primarily uses:

```text id="zdjuxi"
Unit Tests
```

The tests should not require:

- PostgreSQL
- pgvector
- external APIs
- OpenAI
- filesystem access
- network access

---

## 4. Test Data

Tests require controlled `RetrievedChunk` inputs.

Each test retrieval result should contain enough information to verify:

```text id="4w2vwc"
chunk.id
chunk.document_id
chunk.chunk_index
chunk.text
score
```

Example conceptual test data:

```text id="8gw6i7"
Result A
    document_id = DOC-A
    chunk_id = CHUNK-A
    chunk_index = 0
    text = "Python experience"
    score = 0.95

Result B
    document_id = DOC-B
    chunk_id = CHUNK-B
    chunk_index = 3
    text = "FastAPI experience"
    score = 0.85

Result C
    document_id = DOC-C
    chunk_id = CHUNK-C
    chunk_index = 7
    text = "PostgreSQL experience"
    score = 0.75
```

The score values are useful for representing ranked retrieval results but are not expected to appear in `BuiltContext.text`.

---

## 5. Test Case Summary

| ID | Test Case | Design Rule | Expected Result |
|---|---|---|---|
| CB-TC-01 | Empty retrieval | CB-DD-01 | Empty `BuiltContext` |
| CB-TC-02 | Maximum chunks | CB-DD-02 | Only first N results included |
| CB-TC-03 | Preserve retrieval order | CB-DD-03 | Source order equals input order |
| CB-TC-04 | Sequential source numbering | CB-DD-04 | Sources numbered from 1 |
| CB-TC-05 | Context formatting | CB-DD-05 | Exact deterministic text format |
| CB-TC-06 | Source mapping | CB-DD-06 | Each source maps to correct chunk |
| CB-TC-07 | Deterministic output | CB-DD-07 | Same input produces same output |
| CB-TC-08 | Zero `max_chunks` | Error rule | `ValueError` |
| CB-TC-09 | Negative `max_chunks` | Error rule | `ValueError` |
| CB-TC-10 | Results fewer than limit | Edge case | All available results included |

---

# 6. Detailed Test Cases

## CB-TC-01 — Empty Retrieval

### Purpose

Verify that an empty retrieval result is treated as a valid business outcome rather than an error.

### Given

```text id="7jch26"
results = []
```

and a valid `ContextBuilder`.

### When

```text id="uk4a16"
ContextBuilder.build(results)
```

is executed.

### Then

The returned object must be:

```text id="cqj2ab"
BuiltContext(
    text="",
    sources=(),
)
```

The method must not raise an exception.

### Verifies

```text id="1vc2kc"
CB-DD-01 — Empty Retrieval
```

---

## CB-TC-02 — Maximum Chunks

### Purpose

Verify that the builder includes no more than the configured number of retrieval results.

### Given

Three ordered retrieval results:

```text id="wffj8x"
[A, B, C]
```

and:

```text id="7gm8af"
max_chunks = 2
```

### When

```text id="wgrtiz"
build([A, B, C])
```

is executed.

### Then

Only:

```text id="dy41if"
A
B
```

must be included.

The returned context must contain exactly two sources.

```text id="4hxyak"
len(context.sources) == 2
```

`C` must not appear in either:

```text id="nt3ftu"
context.text
context.sources
```

### Verifies

```text id="t7ox1e"
CB-DD-02 — Maximum Chunks
```

---

## CB-TC-03 — Preserve Retrieval Order

### Purpose

Verify that `ContextBuilder` does not perform its own ranking or sorting.

### Given

Retrieval returns results in the order:

```text id="hl17da"
[C, A, B]
```

### When

The context is built.

### Then

The generated source order must remain:

```text id="2xqdr6"
Source 1 → C
Source 2 → A
Source 3 → B
```

The builder must not reorder the results based on:

- document ID
- chunk ID
- chunk index
- text
- score

### Verifies

```text id="ccwrms"
CB-DD-03 — Retrieval Order
```

---

## CB-TC-04 — Sequential Source Numbering

### Purpose

Verify that source numbers begin at `1` and increase sequentially.

### Given

Three retrieval results:

```text id="4xd75q"
[A, B, C]
```

### When

The context is built.

### Then

The source numbers must be:

```text id="rv1al2"
context.sources[0].number == 1
context.sources[1].number == 2
context.sources[2].number == 3
```

The corresponding text markers must be:

```text id="w5cbn9"
[Source 1]
[Source 2]
[Source 3]
```

Source numbering must not begin at `0`.

### Verifies

```text id="w6bnw1"
CB-DD-04 — Source Numbering
```

---

## CB-TC-05 — Context Formatting

### Purpose

Verify that selected chunks are formatted using the exact context format defined by the Detail Design.

### Given

Two retrieval results:

```text id="4q2gm8"
A.text = "Python experience"
B.text = "FastAPI experience"
```

### When

The context is built.

### Then

`context.text` must exactly equal:

```text id="3kjm2p"
[Source 1]
Python experience

[Source 2]
FastAPI experience
```

Each source must:

1. start with `[Source N]`
2. place chunk text on the following line
3. be separated from the next source by one blank line

Retrieval scores must not appear in the formatted context.

### Verifies

```text id="s8b84i"
CB-DD-05 — Context Formatting
```

---

## CB-TC-06 — Source Mapping

### Purpose

Verify that every source marker maps to the correct original chunk.

### Given

A retrieval result with:

```text id="l31mtv"
document_id = DOC-A
chunk_id = CHUNK-A
chunk_index = 4
text = "Python experience"
```

### When

The context is built.

### Then

the first `ContextSource` must contain:

```text id="5c7k1p"
number = 1
document_id = DOC-A
chunk_id = CHUNK-A
chunk_index = 4
text = "Python experience"
```

The formatted text:

```text id="u1obge"
[Source 1]
Python experience
```

must therefore correspond to that same `ContextSource`.

For multiple results:

```text id="x4gwwv"
[Source N]
```

must map to:

```text id="j86uxx"
context.sources[N - 1]
```

### Verifies

```text id="w62ux7"
CB-DD-06 — Source Mapping
```

---

## CB-TC-07 — Deterministic Output

### Purpose

Verify that context construction is deterministic.

### Given

The same ordered retrieval results:

```text id="3k9oyn"
[A, B, C]
```

and the same:

```text id="vdddbm"
max_chunks
```

### When

The builder is called twice:

```text id="jnh4hn"
first = build(results)
second = build(results)
```

### Then

both results must be equal:

```text id="tdr5g3"
first == second
```

Specifically:

```text id="0w6u9r"
first.text == second.text
first.sources == second.sources
```

No random values or external state may affect the result.

### Verifies

```text id="8v9xjj"
CB-DD-07 — Deterministic Output
```

---

## CB-TC-08 — Reject Zero `max_chunks`

### Purpose

Verify validation of an invalid zero chunk limit.

### Given

```text id="4h0vje"
max_chunks = 0
```

### When

`ContextBuilder` is constructed.

### Then

construction must raise:

```text id="p4mtc8"
ValueError
```

The error must occur before `build()` is called.

### Verifies

The invalid-configuration rule defined in Detail Design.

---

## CB-TC-09 — Reject Negative `max_chunks`

### Purpose

Verify validation of a negative chunk limit.

### Given

```text id="t0pn6e"
max_chunks = -1
```

### When

`ContextBuilder` is constructed.

### Then

construction must raise:

```text id="cj5z7m"
ValueError
```

No `ContextBuilder` instance with an invalid negative limit should be created.

### Verifies

The invalid-configuration rule defined in Detail Design.

---

## CB-TC-10 — Results Fewer Than Maximum

### Purpose

Verify that the builder correctly handles fewer retrieval results than the configured maximum.

### Given

```text id="5qvg13"
results = [A, B]
max_chunks = 5
```

### When

The context is built.

### Then

both available results must be included:

```text id="n3fdg4"
Source 1 → A
Source 2 → B
```

The builder must not:

- add empty sources
- duplicate existing results
- create Sources 3–5

The returned source count must be:

```text id="3bh0mf"
len(context.sources) == 2
```

### Verifies

The `max_chunks` boundary behavior defined by `CB-DD-02`.

---

# 7. Traceability Matrix

| Detail Design | Behavior | Test Coverage |
|---|---|---|
| CB-DD-01 | Empty retrieval | CB-TC-01 |
| CB-DD-02 | Maximum chunks | CB-TC-02, CB-TC-10 |
| CB-DD-03 | Preserve retrieval order | CB-TC-03 |
| CB-DD-04 | Source numbering | CB-TC-04 |
| CB-DD-05 | Context formatting | CB-TC-05 |
| CB-DD-06 | Source mapping | CB-TC-06 |
| CB-DD-07 | Deterministic output | CB-TC-07 |
| Error rule | `max_chunks > 0` | CB-TC-08, CB-TC-09 |

All Detail Design rules must have at least one corresponding test case.

---

# 8. Expected Test Characteristics

Context Builder tests must be:

### Deterministic

The same test input must always produce the same expected output.

### Isolated

Tests must not require database, filesystem, network, embedding, or LLM access.

### Fast

The entire Context Builder unit-test suite should execute locally without external infrastructure.

### Explicit

Tests should verify actual values rather than only checking that the method does not raise an exception.

For example, prefer verifying:

```text id="3epfn7"
context.sources[0].document_id == expected_document_id
```

rather than only:

```text id="kwz5qq"
len(context.sources) > 0
```

---

# 9. Exit Criteria

Phase 3.1 Context Builder testing is complete when:

- CB-TC-01 through CB-TC-10 pass
- all Detail Design rules have corresponding test coverage
- tests run without external services
- existing project tests continue to pass
- Ruff reports no new issues
- implementation behavior matches the documented Detail Design