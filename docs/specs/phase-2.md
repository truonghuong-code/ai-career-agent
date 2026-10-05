# Phase 2 Specification — Retrieval Quality & Document Lifecycle

## 1. Overview

Phase 2 improves the reliability, manageability, and retrieval quality of the document RAG foundation implemented in Phase 1.

Phase 1 already provides:

- document ingestion
- TXT, Markdown, PDF, and DOCX parsing
- deterministic text chunking
- embedding generation
- PostgreSQL + pgvector persistence
- semantic similarity search
- document ownership scoping
- document processing status
- local source-file storage

Phase 2 does not replace this architecture.

Instead, it formalizes document lifecycle behavior, adds document management capabilities, improves text preparation and chunking behavior, and strengthens retrieval filtering and retrieval quality guarantees.

---

# 2. Goals

Phase 2 must provide:

1. A clearly defined document lifecycle.
2. Safe document deletion.
3. Owner-scoped document listing.
4. Deterministic text normalization.
5. More reliable chunk generation.
6. Explicit retrieval filtering.
7. A stable retrieval result contract.
8. Integration and unit tests covering retrieval and lifecycle behavior.

At the end of Phase 2, the retrieval subsystem should be stable enough to support Phase 3 LLM grounded answer generation.

---

# 3. Non-Goals

The following are explicitly outside Phase 2:

- LLM answer generation
- RAG prompt construction
- citations in generated answers
- CV analysis
- JD analysis
- skill-gap analysis
- learning-plan generation
- agent orchestration
- interview simulation
- Japanese communication coaching
- authentication
- authorization framework
- background job processing
- Redis/RQ/Celery processing
- cloud object storage
- reranking models
- hybrid lexical/vector search
- production observability infrastructure

`X-Internal-User-ID` continues to provide temporary ownership scoping.

It must not be considered authentication.

---

# 4. Existing Document Lifecycle

The current ingestion implementation creates a document directly in the `PROCESSING` state.

Although `PENDING` exists in `DocumentStatus`, synchronous ingestion currently does not use it.

The effective lifecycle is:

```text
PROCESSING
    |
    +---- success ----> COMPLETED
    |
    +---- failure ----> FAILED
```

Phase 2 must formalize and test this existing behavior rather than introduce unnecessary lifecycle states.

---

# 5. Phase 2.1 — Document Lifecycle

## 5.1 Requirements

When document ingestion starts:

- a `Document` record must be created
- its owner must be recorded
- its processing status must be `PROCESSING`

When ingestion succeeds:

- processing status must become `COMPLETED`
- `error_message` must be `NULL`
- `extracted_text_length` must contain the extracted text length
- generated chunks must be associated with the document

When ingestion fails:

- processing status must become `FAILED`
- `error_message` must contain useful failure information
- the document must remain inspectable by its owner

Only `COMPLETED` documents may participate in semantic retrieval.

## 5.2 Success Scenario

Input:

- supported document
- valid content
- working parser
- working embedding provider

Expected state:

```text
Document
processing_status = COMPLETED
error_message = NULL
extracted_text_length > 0
```

Expected result:

- ingestion returns successfully
- at least one chunk exists for non-empty processable text
- source file remains stored

## 5.3 Failure Scenario

Input:

- supported document whose processing fails during extraction, embedding, or another ingestion operation

Expected state:

```text
Document
processing_status = FAILED
error_message != NULL
```

The failure must not cause the document to appear in retrieval results.

## 5.4 PENDING Status

`PENDING` remains part of the existing enum for possible future asynchronous processing.

Phase 2 must not introduce artificial `PENDING → PROCESSING` transitions while ingestion remains synchronous.

---

# 6. Phase 2.2 — Document Deletion

## 6.1 Requirements

An owner must be able to delete one of their own documents.

Deletion must be owner-scoped.

A user must not be able to delete a document belonging to another owner.

Deleting a document must remove:

- the `Document` database record
- all associated `DocumentChunk` records
- the corresponding locally stored source file when applicable

## 6.2 Chunk Deletion

`document_chunks.document_id` already uses:

```text
ON DELETE CASCADE
```

Therefore deleting the parent document must result in deletion of its chunks.

Application behavior must rely on and verify this relationship rather than manually introducing duplicate deletion logic without need.

## 6.3 Source File

Database deletion and source-file deletion must be coordinated by the service layer.

The system must avoid intentionally leaving orphaned source files after successful document deletion.

## 6.4 Ownership

Given:

```text
document.owner_id = user-a
```

a deletion request from:

```text
user-b
```

must not delete the document.

The external behavior should not expose another owner's document.

## 6.5 Missing Document

Deleting a nonexistent document or a document outside the current ownership scope must produce the API's defined not-found behavior.

---

# 7. Phase 2.3 — Document Listing

## 7.1 Requirements

The system must allow an owner to list their documents.

Returned documents must belong only to the requested owner.

A document listing should expose the existing document metadata required by clients, including where applicable:

- document ID
- filename
- MIME type
- document type
- processing status
- size
- extracted text length
- error information
- creation/update timestamps

## 7.2 Ownership

A request scoped to `user-a` must never return documents owned by `user-b`.

## 7.3 Status

Listing may include documents in:

- `PROCESSING`
- `COMPLETED`
- `FAILED`

because listing is a management operation rather than semantic retrieval.

## 7.4 Ordering

Document listing must use deterministic ordering.

The implementation should define an explicit default order rather than relying on database row order.

## 7.5 Filtering

Status filtering may be supported where useful.

Filtering must remain explicit and owner-scoped.

Pagination should only be introduced if required by the API design for this phase; unnecessary pagination abstractions should not be added preemptively.

---

# 8. Phase 2.4 — Text Normalization

## 8.1 Purpose

Documents extracted from different formats may contain inconsistent whitespace and line formatting.

Normalization should produce more predictable input for chunking and embeddings.

## 8.2 Requirements

Normalization must be deterministic.

Given the same input text, it must always produce the same output.

Normalization may handle:

- line-ending normalization
- unnecessary repeated whitespace
- excessive blank lines
- leading/trailing whitespace

Normalization must not intentionally change semantic content.

## 8.3 Preservation

Normalization must avoid destroying meaningful text structure where that structure may be useful for retrieval.

Examples include:

- paragraph boundaries
- headings
- list structure where reasonably preserved by extraction

## 8.4 Empty Content

Normalization must handle empty or whitespace-only input predictably.

The ingestion behavior for content that becomes empty after normalization must be explicitly tested.

---

# 9. Phase 2.5 — Chunking Improvements

## 9.1 Requirements

Chunking must remain deterministic.

Given:

```text
same normalized text
same chunk_size
same chunk_overlap
```

the chunker must produce the same chunks.

Each chunk must continue to provide:

- chunk index
- text
- character start offset
- character end offset

## 9.2 Chunk Size

Chunk size must respect the configured chunking strategy.

The implementation must avoid generating unnecessary empty chunks.

## 9.3 Overlap

Chunk overlap must preserve contextual continuity between adjacent chunks.

Overlap configuration must not produce invalid or non-progressing chunk boundaries.

## 9.4 Metadata

Chunk metadata must remain associated with the source document/extraction metadata where applicable.

## 9.5 Scope

Phase 2 does not require:

- semantic chunking models
- LLM-based chunking
- sentence-transformer-based segmentation
- document-layout-aware chunking

These may be evaluated later if retrieval quality requires them.

---

# 10. Phase 2.6 — Retrieval Filtering

## 10.1 Existing Behavior

Phase 1 retrieval already filters by:

- chunk owner
- document owner
- document processing status
- optional document IDs

Phase 2 must formalize and test this behavior.

## 10.2 Ownership

Search results for `user-a` must never contain chunks owned by `user-b`.

Both document ownership and chunk ownership must remain scoped.

## 10.3 Document Status

Only documents with:

```text
processing_status = COMPLETED
```

may appear in semantic retrieval.

`PROCESSING` and `FAILED` documents must not appear.

## 10.4 Document ID Filter

When `document_ids` are supplied:

- results must belong only to those documents
- ownership restrictions must still apply
- supplying another owner's document ID must not bypass ownership filtering

## 10.5 Limit

The requested result limit must be respected.

The system must not return more results than requested.

---

# 11. Phase 2.7 — Retrieval Result Model

## 11.1 Purpose

Retrieval output must provide a stable internal contract for future consumers, especially Phase 3.

A retrieval result must provide enough information to identify:

- retrieved text
- source chunk
- source document
- retrieval score

## 11.2 Required Information

The retrieval result must make available:

- chunk ID
- document ID
- chunk index
- chunk text
- similarity score
- relevant chunk metadata
- relevant source document metadata

## 11.3 Similarity Score

The retrieval score must have consistent semantics.

Higher score must represent a better semantic match.

The retrieval layer must not expose raw distance as though it were similarity.

## 11.4 Separation

Database ORM models must not become the public API contract directly.

API responses must continue to use explicit Pydantic schemas.

Internal repository/service result models may wrap database entities where appropriate.

---

# 12. Phase 2.8 — Retrieval Quality Tests

Phase 2 must include tests for important retrieval guarantees.

## 12.1 Required Scenarios

Tests must cover at minimum:

### Ownership isolation

```text
user-a search
→ never returns user-b chunks
```

### Document filtering

```text
search(document_ids=[A])
→ results belong to A
```

### Completed-only retrieval

```text
COMPLETED → searchable
FAILED → not searchable
PROCESSING → not searchable
```

### Result limit

```text
limit = N
→ number of results <= N
```

### Deterministic behavior

Where deterministic embeddings are used in tests, repeated equivalent retrieval operations should produce stable behavior.

## 12.2 Test Levels

Unit tests should be used for isolated deterministic behavior such as:

- normalization
- chunking
- result transformation where applicable

Integration tests should be used for behavior involving:

- service
- repository
- PostgreSQL/pgvector
- document lifecycle
- ownership filtering
- deletion
- retrieval

---

# 13. Ownership and Security Constraints

All document operations must remain owner-scoped.

Repository queries involving user documents must include ownership constraints where appropriate.

Phase 2 must not weaken the ownership isolation implemented in Phase 1.

`X-Internal-User-ID` is temporary infrastructure and must not be described as secure authentication.

Authentication is deferred to a later phase.

---

# 14. Database Constraints

Phase 2 should reuse the existing database schema where possible.

A new Alembic migration is required only when the database schema actually changes.

Historical migrations must never be edited to implement Phase 2.

The existing cascade relationship between documents and chunks should be preserved.

---

# 15. API Constraints

Existing Phase 1 APIs must remain compatible unless a Phase 2 requirement explicitly requires a change.

New document management endpoints may be added for:

- listing documents
- deleting documents

API endpoints must remain thin.

Business workflow decisions belong in services.

Database access belongs in repositories.

The intended dependency direction remains:

```text
API
 ↓
Service
 ↓
Repository
 ↓
Database
```

---

# 16. Error Handling

Expected domain/processing errors must be converted into controlled application behavior.

Internal implementation details must not be unnecessarily exposed through HTTP responses.

Useful failure information may be stored in `Document.error_message` for document inspection and debugging.

Unexpected failures should remain distinguishable from expected validation or not-found conditions.

---

# 17. Acceptance Criteria

Phase 2 is complete when:

- document lifecycle behavior is explicitly tested
- successful ingestion ends in `COMPLETED`
- failed ingestion ends in `FAILED`
- failed documents contain error information
- only completed documents are searchable
- owners can list their own documents
- owners can delete their own documents
- deletion removes associated chunks
- deletion handles the source file correctly
- ownership isolation is preserved
- text normalization is deterministic
- chunking behavior is deterministic and tested
- retrieval document filtering is tested
- retrieval result structure is stable
- retrieval limit behavior is tested
- unit tests pass
- integration tests pass
- Ruff passes
- existing Phase 1 behavior remains functional

---

# 18. Definition of Done

Phase 2 may be considered done only when implementation, tests, and documentation describe the same behavior.

Before merging Phase 2:

```text
Spec
  ↕
Detail Design
  ↕
Implementation
  ↕
Tests
```

must be consistent.

Any meaningful architecture decision discovered during implementation should either update the architecture documentation or be recorded as an ADR when appropriate.