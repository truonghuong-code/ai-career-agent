# 3.1 — Context Builder Detail Design

## 1. Purpose

`ContextBuilder` is responsible for converting ranked retrieval results into deterministic context for the LLM while preserving source information for later citation and traceability.

The component sits between the retrieval layer and the prompt-building layer.

```text
Retrieval
    ↓
RetrievedChunk[]
    ↓
ContextBuilder
    ↓
BuiltContext
    ↓
PromptBuilder
```

---

## 2. Responsibilities

`ContextBuilder` is responsible for:

- receiving ranked retrieval results
- selecting up to the configured maximum number of chunks
- preserving retrieval order
- assigning deterministic source numbers
- formatting retrieved text into LLM-ready context
- preserving source-to-chunk mappings for later citation

Conceptually:

```text
ranked retrieval results
        ↓
select relevant chunks
        ↓
preserve retrieval order
        ↓
build deterministic context
        ↓
preserve source mapping
```

`ContextBuilder` does not:

- perform vector search
- generate embeddings
- re-rank retrieval results
- access the database directly
- call the LLM
- construct LLM instructions
- decide how the LLM should answer the user's question

---



## 3. Components



### 3.1 `ContextBuilder`

Responsible for transforming retrieval results into a `BuiltContext`.

Proposed location:

```text
app/rag/context.py
```

Primary interface:

```text
ContextBuilder.build(
    results: Sequence[RetrievedChunk]
) -> BuiltContext
```



### 3.2 `ContextSource`

Represents one source included in the generated context.

Structure:

```text
ContextSource
    number: int
    document_id: UUID
    chunk_id: UUID
    chunk_index: int
    text: str
```

`number` corresponds to the source marker used in the formatted context.

For example:

```text
[Source 2]
```

maps to:

```text
ContextSource(number=2)
```



### 3.3 `BuiltContext`

Represents the final output produced by `ContextBuilder`.

Structure:

```text
BuiltContext
    text: str
    sources: tuple[ContextSource, ...]
```

`text` is intended for the prompt-building layer.

`sources` preserves structured source information for later citation and response construction.

---



## 4. Input

`ContextBuilder.build()` receives an ordered sequence of `RetrievedChunk` objects.

```text
Sequence[RetrievedChunk]
```

The input order is assumed to represent the ranking determined by the retrieval layer.

For example:

```text
RetrievedChunk A   ← highest ranked
RetrievedChunk B
RetrievedChunk C
RetrievedChunk D   ← lowest ranked
```

`ContextBuilder` must preserve this order and must not perform additional ranking.

Each `RetrievedChunk` provides access to the retrieved `DocumentChunk` and its retrieval score.

The Context Builder uses the chunk identity and text required for context construction. Retrieval score is not included in the generated LLM context in Phase 3.1.

---



## 5. Output

`ContextBuilder.build()` always returns a `BuiltContext`.

```text
BuiltContext
├── text: str
└── sources: tuple[ContextSource, ...]
```



### `text`

Contains the formatted context supplied to the prompt-building layer.

Example:

```text
[Source 1]
Candidate has 3 years of AI experience.

[Source 2]
The position requires Python and FastAPI.
```



### `sources`

Contains the ordered source metadata corresponding to the source markers in `text`.

Example:

```text
sources[0]
    number = 1
    document_id = ...
    chunk_id = ...
    chunk_index = ...
    text = "Candidate has 3 years of AI experience."
```

Therefore:

```text
[Source 1]
     ↓
ContextSource(number=1)
     ↓
document_id
chunk_id
chunk_index
text
```

---



## 6. Processing Flow

```text
RetrievedChunk[]
        |
        v
check empty input
        |
        v
select first max_chunks results
        |
        v
preserve retrieval order
        |
        v
assign source numbers starting from 1
        |
        v
create ContextSource for each result
        |
        v
format [Source N] section for each result
        |
        v
join sections with a blank line
        |
        v
BuiltContext
```

The builder does not modify the ranking produced by retrieval.

---



## 7. Processing Rules



### DD-01 — Empty Retrieval

If the input sequence contains no retrieval results, the builder returns an empty `BuiltContext`.

```text
BuiltContext(
    text="",
    sources=(),
)
```

An empty retrieval result is considered a valid business outcome, not an error.

---



### DD-02 — Maximum Chunks

`ContextBuilder` has a configurable `max_chunks` value.

Only the first `max_chunks` retrieval results are included.

Example:

```text
Input:

A
B
C
D

max_chunks = 2
```

Selected results:

```text
A
B
```

Results beyond the limit are ignored.

---



### DD-03 — Retrieval Order

`ContextBuilder` must preserve the order supplied by the retrieval layer.

It must not:

- sort by score
- perform additional similarity calculations
- re-rank results

Given:

```text
A
B
C
```

the generated sources must remain:

```text
Source 1 → A
Source 2 → B
Source 3 → C
```

---



### DD-04 — Source Numbering

Sources are numbered sequentially starting from `1`.

Example:

```text
RetrievedChunk A → Source 1
RetrievedChunk B → Source 2
RetrievedChunk C → Source 3
```

Source numbering is deterministic for the same ordered input and configuration.

---



### DD-05 — Context Formatting

Each selected retrieval result is formatted as:

```text
[Source N]
<chunk text>
```

Multiple source sections are separated by one blank line.

Example:

```text
[Source 1]
Candidate has 3 years of AI experience.

[Source 2]
The position requires Python and FastAPI.
```

Retrieval scores are not included in the formatted context.

---



### DD-06 — Source Mapping

Every formatted source marker must have exactly one corresponding `ContextSource`.

Example:

```text
[Source 2]
     ↓
ContextSource(number=2)
     ↓
document_id
chunk_id
chunk_index
text
```

The order of `BuiltContext.sources` must match the source numbering used in `BuiltContext.text`.

Therefore:

```text
sources[0].number == 1
sources[1].number == 2
sources[2].number == 3
```

---



### DD-07 — Deterministic Output

For the same:

```text
retrieval results
+
retrieval order
+
max_chunks
```

`ContextBuilder` must produce the same:

```text
BuiltContext.text
BuiltContext.sources
```

No randomness or external service calls are permitted during context construction.

---



## 8. Edge Cases



### Empty Input

```text
results = []
```

returns:

```text
BuiltContext(
    text="",
    sources=(),
)
```



### Fewer Results Than `max_chunks`

If:

```text
results count = 2
max_chunks = 5
```

both results are included.

No padding or duplicated sources are added.

### More Results Than `max_chunks`

If:

```text
results count = 10
max_chunks = 5
```

only the first five results are included.

### Invalid `max_chunks`

`max_chunks` must be greater than zero.

Values such as:

```text
0
-1
```

are invalid configuration.

---



## 9. Error Handling

Empty retrieval results are not considered an error.

They return an empty `BuiltContext`.

Invalid builder configuration is considered a programming/configuration error.

If:

```text
max_chunks <= 0
```

`ContextBuilder` raises:

```text
ValueError
```

`ContextBuilder` must not catch unrelated exceptions from malformed or unexpected retrieval objects merely to return an empty context.

Unexpected programming errors should propagate to the caller rather than being silently converted into valid empty results.

---



## 10. Dependencies

`ContextBuilder` may depend on the retrieval result contract produced by the retrieval layer:

```text
RetrievedChunk
```

It must not directly depend on:

```text
AsyncSession
DocumentRepository
EmbeddingProvider
PostgreSQL
pgvector
LLMProvider
```

Dependency direction:

```text
DocumentRepository
        ↓
RetrievedChunk[]
        ↓
DocumentSearchService
        ↓
ContextBuilder
        ↓
BuiltContext
        ↓
PromptBuilder
```

`ContextBuilder` itself performs no database, network, embedding, or LLM operations.

---



## 11. Out of Scope

Phase 3.1 does not implement:

- vector retrieval
- embedding generation
- retrieval re-ranking
- token counting
- token-budget optimization
- prompt instructions
- user-question formatting
- LLM invocation
- answer generation
- citation validation against LLM output
- API response generation

Token-based context budgeting may be introduced later when the LLM provider and model-specific constraints are defined.

Phase 3.1 is limited to:

```text
RetrievedChunk[]
        ↓
deterministic context construction
        ↓
BuiltContext
```

