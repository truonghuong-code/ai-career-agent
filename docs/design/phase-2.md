# Phase 2 Detailed Design — Retrieval Quality & Document Lifecycle

## 1. Purpose

This document describes the implementation design for Phase 2 — Retrieval Quality & Document Lifecycle.

It translates the Phase 2 specification into component responsibilities, execution flows, repository operations, API behavior, and test strategy.

The design intentionally builds on the existing Phase 1 architecture instead of introducing a new framework or abstraction layer.

---

# 2. Architecture Principles

Phase 2 must preserve the existing dependency direction:

```text
API
 │
 ▼
Service
 │
 ▼
Repository
 │
 ▼
PostgreSQL / pgvector
```

Supporting components remain:

```text
Parser
Chunker
EmbeddingProvider
Storage
```

Responsibilities must remain separated.

## API

Responsible for:

- HTTP input
- request validation
- dependency construction
- HTTP status mapping
- Pydantic response schemas

The API must not contain database query logic or document workflow logic.

## Service

Responsible for:

- application workflow
- coordinating repositories
- coordinating storage
- lifecycle decisions
- document deletion workflow
- retrieval orchestration

## Repository

Responsible for:

- SQLAlchemy persistence
- owner-scoped queries
- pgvector queries
- database filtering
- database deletion

## RAG Components

Responsible for:

- parsing
- normalization
- chunking
- embeddings

They must not depend on FastAPI or HTTP behavior.

---

# 3. Current Phase 1 Ingestion Flow

The existing flow is:

```text
HTTP upload
    |
    v
DocumentIngestionService.ingest()
    |
    +--> parser registry
    |
    +--> checksum
    |
    +--> local storage.save()
    |
    +--> repository.create_document()
    |       |
    |       +--> PROCESSING
    |
    +--> parser.extract()
    |
    +--> chunker.split()
    |
    +--> embedding_provider.embed()
    |
    +--> repository.add_chunks()
    |
    +--> repository.complete_document()
            |
            +--> COMPLETED
```

Failure path:

```text
processing exception
       |
       v
repository.fail_document()
       |
       v
FAILED
```

This remains the basis of Phase 2.

---

# 4. Phase 2.1 — Document Lifecycle Design

## 4.1 State Model

The effective synchronous state model remains:

```text
             +----------------+
             |   PROCESSING   |
             +----------------+
                |          |
          success          failure
                |          |
                v          v
        +-----------+   +--------+
        | COMPLETED |   | FAILED |
        +-----------+   +--------+
```

`PENDING` remains defined but unused by the synchronous ingestion flow.

No new lifecycle state is required.

---

## 4.2 Creation

`DocumentRepository.create_document()` continues to create documents with:

```text
processing_status = PROCESSING
```

This operation should not decide parsing or embedding behavior.

---

## 4.3 Completion

After successful:

```text
extract
→ normalize
→ chunk
→ embed
→ persist chunks
```

the service calls:

```text
repository.complete_document(...)
```

Expected state:

```text
processing_status = COMPLETED
extracted_text_length = normalized/extracted text length according to
the final agreed ingestion contract
error_message = NULL
```

The exact meaning of `extracted_text_length` must remain consistent once normalization is introduced.

The implementation must choose and test whether this field represents raw extracted text or normalized text. It must not silently vary between document types.

Preferred design for Phase 2:

```text
extracted_text_length = length of extracted source text
```

because the field is named `extracted_text_length`, while normalization is a downstream transformation.

---

## 4.4 Failure

Expected processing failures continue through:

```text
repository.fail_document(document, message)
```

Expected state:

```text
processing_status = FAILED
error_message = failure information
```

The service remains responsible for deciding that ingestion has failed.

The repository remains responsible only for persisting the new state.

---

## 4.5 Transaction Consideration

Current Phase 1 behavior uses `flush()` during document/chunk creation and `commit()` during completion/failure.

Phase 2 tests must verify the resulting database state on failures.

A transaction redesign must not be introduced solely for architectural neatness.

If tests demonstrate that partial chunks are committed for failed ingestion in an undesirable state, transaction handling should then be adjusted deliberately.

Desired invariant:

```text
FAILED document
→ must not be retrievable
```

A stronger invariant may be adopted if needed:

```text
FAILED document
→ no persisted chunks
```

but this should be implemented only after confirming expected behavior through tests.

---

# 5. Phase 2.2 — Document Deletion Design

## 5.1 Proposed Flow

```text
DELETE request
      |
      v
API
      |
      v
DocumentManagementService
      |
      +--> repository.get_document(document_id, owner_id)
      |
      +--> not found?
      |       |
      |       +--> return not-found behavior
      |
      +--> capture storage_path
      |
      +--> repository.delete_document(...)
      |
      +--> delete source file
      |
      v
success
```

The exact ordering between database deletion and file deletion must be handled carefully because local filesystem operations and PostgreSQL do not share one transaction.

---

## 5.2 Service Responsibility

Deletion affects two resources:

```text
PostgreSQL
+
local filesystem
```

Therefore orchestration belongs in the service layer.

The API must not perform both operations directly.

---

## 5.3 Repository Operation

Add an owner-scoped repository operation conceptually equivalent to:

```text
delete_document(document_id, owner_id)
```

It must never perform an unscoped deletion by document ID when called from user-facing document management.

---

## 5.4 Chunk Cascade

Existing relationship:

```text
Document
   |
   +--> DocumentChunk
```

uses database:

```text
ON DELETE CASCADE
```

and SQLAlchemy relationship cascade configuration.

Therefore deleting a `Document` should delete associated chunks without manually issuing one delete per chunk.

Integration tests must verify this behavior.

---

## 5.5 Local Storage

`LocalDocumentStorage` should expose deletion behavior rather than allowing the service to manipulate arbitrary filesystem paths directly.

Conceptually:

```text
storage.delete(storage_path)
```

Storage deletion should be constrained to the configured document storage area.

Missing source files should have explicitly defined behavior.

Preferred behavior:

- database ownership must still be enforced
- an already-missing source file should not create an orphaned database document solely because filesystem cleanup was impossible
- unexpected filesystem failures should be surfaced/logged appropriately

Exact failure semantics should be covered by tests before adding complex compensation logic.

---

# 6. Phase 2.3 — Document Listing Design

## 6.1 Flow

```text
GET documents
     |
     v
API
     |
     v
DocumentManagementService
     |
     v
DocumentRepository.list_documents(owner_id, ...)
     |
     v
PostgreSQL
```

If listing remains simple and contains no workflow logic, direct API → repository usage may technically work.

However, document management behavior should preferably be grouped consistently in a service once deletion/listing operations grow.

Avoid creating a service that merely exists as a pass-through unless it improves consistency or is required for future workflow.

---

## 6.2 Repository Query

The listing query must include:

```text
WHERE documents.owner_id = :owner_id
```

Optional status filtering should add:

```text
AND processing_status = :status
```

Ordering must be explicit.

Recommended default:

```text
created_at DESC
```

with a deterministic secondary key if required.

---

## 6.3 API Response

Use Pydantic response schemas.

Do not expose SQLAlchemy `Document` instances as the API contract.

Existing document response structures should be reused where they already satisfy the requirement.

---

# 7. Phase 2.4 — Text Normalization Design

## 7.1 Position in Pipeline

Normalization should occur after extraction and before chunking.

New flow:

```text
parser.extract()
      |
      v
raw extracted text
      |
      v
normalize()
      |
      v
normalized text
      |
      v
chunker.split()
```

Embedding receives chunk text derived from normalized text.

---

## 7.2 Component

Normalization should be implemented as a small deterministic RAG utility/component rather than placed in:

- API
- repository
- database model

Possible responsibility:

```text
app/rag/normalization.py
```

Exact naming should follow existing project conventions.

---

## 7.3 Normalization Rules

Initial normalization should remain conservative.

Candidate operations:

```text
CRLF/CR → LF

trim unnecessary leading/trailing whitespace

reduce excessive blank lines

normalize clearly redundant whitespace where safe
```

Avoid aggressive transformations such as:

- removing all line breaks
- changing case globally
- removing punctuation
- removing Japanese characters
- removing accents
- stemming
- stop-word removal

Those transformations may damage retrieval semantics.

---

## 7.4 Testing

Normalization is deterministic and should primarily use unit tests.

Examples:

```text
Windows line endings
→ normalized line endings

excessive blank lines
→ bounded blank lines

leading/trailing whitespace
→ trimmed

same input twice
→ same output
```

---

# 8. Phase 2.5 — Chunking Improvement Design

## 8.1 Existing Component

Continue using:

```text
DeterministicTextChunker
```

unless tests demonstrate a concrete limitation requiring redesign.

Do not replace it with LangChain solely for convenience.

---

## 8.2 Input

Chunker input becomes:

```text
normalized text
```

rather than inconsistent raw extracted text.

---

## 8.3 Required Invariants

For generated chunks:

```text
chunk.index >= 0

char_start >= 0

char_end > char_start

chunk.text != ""

chunks ordered by index

overlap does not prevent forward progress
```

Offsets must remain consistent with the text representation being chunked.

After normalization is introduced, offsets therefore refer to:

```text
normalized text
```

unless explicitly documented otherwise.

---

## 8.4 Configuration Validation

Invalid configurations such as conceptually:

```text
chunk_overlap >= chunk_size
```

must not create infinite/non-progressing chunk generation.

Configuration should either:

- reject invalid values, or
- have explicitly defined safe behavior

Rejecting invalid configuration is preferred when the values cannot produce meaningful chunks.

---

# 9. Phase 2.6 — Retrieval Filtering Design

## 9.1 Existing Query

Phase 1 already performs a join:

```text
DocumentChunk
      |
      v
Document
```

and filters approximately by:

```text
DocumentChunk.owner_id == owner_id
Document.owner_id == owner_id
Document.processing_status == COMPLETED
```

This must be preserved.

---

## 9.2 Query Flow

```text
query text
    |
    v
EmbeddingProvider.embed()
    |
    v
query vector
    |
    v
DocumentRepository.search()
    |
    +--> owner filter
    |
    +--> COMPLETED filter
    |
    +--> optional document_ids filter
    |
    +--> cosine distance
    |
    +--> order
    |
    +--> limit
    |
    v
RetrievedChunk[]
```

---

## 9.3 Ownership Defense

Both:

```text
DocumentChunk.owner_id
```

and:

```text
Document.owner_id
```

remain filtered.

Although this may appear redundant, it provides consistency checking against malformed/corrupt ownership relationships and preserves the current Phase 1 isolation behavior.

Do not remove it without a deliberate schema/invariant decision.

---

## 9.4 Document ID Filter

Optional `document_ids` must be combined with owner filtering.

It must never replace owner filtering.

Correct conceptual condition:

```text
owner = current owner
AND
document status = COMPLETED
AND
document_id IN requested IDs
```

Not:

```text
owner filter
OR
document_id IN requested IDs
```

---

# 10. Phase 2.7 — Retrieval Result Model Design

## 10.1 Existing Internal Model

Phase 1 currently uses:

```text
RetrievedChunk
    chunk: DocumentChunk
    score: float
```

This can remain an internal repository result while Phase 2 evaluates whether a more explicit service-level model is needed.

Do not create another DTO solely to duplicate identical data.

---

## 10.2 Score

Current query calculates cosine distance and transforms it conceptually into:

```text
similarity = 1 - cosine_distance
```

Therefore:

```text
higher score = better match
```

This semantic must remain consistent for downstream Phase 3.

---

## 10.3 API Boundary

The API must map internal retrieval results into a Pydantic schema such as the existing:

```text
DocumentSearchResult
```

SQLAlchemy models must not become the HTTP response contract.

---

## 10.4 Future Phase 3 Compatibility

Phase 3 will need retrieval context approximately containing:

```text
text
document identity
source metadata
chunk identity
similarity score
```

Phase 2 should make these available without introducing LLM-specific behavior into the repository.

Repository search must remain retrieval-focused.

---

# 11. Phase 2.8 — Retrieval Quality Test Design

## 11.1 Unit Tests

Primary unit-test targets:

```text
tests/unit/
```

Expected coverage:

### Normalization

```text
raw text
→ expected normalized text
```

### Chunking

```text
normalized text
→ deterministic chunks
```

Validate:

- boundaries
- overlap
- offsets
- empty input
- invalid configuration where applicable

---

## 11.2 Integration Tests

Primary integration-test targets:

```text
tests/integration/
```

Integration tests should use real project components where practical:

```text
Service
Repository
PostgreSQL/pgvector
Storage
```

Deterministic embeddings remain appropriate because tests should not depend on an external embedding API.

---

## 11.3 Lifecycle Test — Success

Arrange:

```text
valid document
working parser
deterministic embedding provider
test database
test storage
```

Act:

```text
DocumentIngestionService.ingest()
```

Assert:

```text
document exists

processing_status == COMPLETED

error_message is None

extracted_text_length is populated

chunk_count > 0

source file exists
```

---

## 11.4 Lifecycle Test — Failure

Arrange a controlled processing failure.

Prefer a deterministic test double that fails at a known boundary, for example the embedding provider.

Act:

```text
DocumentIngestionService.ingest()
```

Assert:

```text
expected exception raised

document remains inspectable

processing_status == FAILED

error_message is populated
```

Then verify that the failed document cannot participate in retrieval.

---

## 11.5 Ownership Test

Create:

```text
user-a document
user-b document
```

Search as:

```text
user-a
```

Assert:

```text
all results belong to user-a
```

---

## 11.6 Document Filter Test

Create multiple completed documents for the same owner.

Search using:

```text
document_ids = [document A]
```

Assert:

```text
all results.document_id == A
```

---

## 11.7 Status Filter Test

Prepare documents representing relevant lifecycle states.

Assert:

```text
COMPLETED → may appear

PROCESSING → never appears

FAILED → never appears
```

---

## 11.8 Deletion Test

Arrange:

```text
ingested document
+
persisted chunks
+
stored source file
```

Act:

```text
delete document
```

Assert:

```text
document no longer exists

associated chunks no longer exist

source file no longer exists
```

Also test:

```text
user-b attempts to delete user-a document
→ document remains unchanged
```

---

# 12. Proposed Component Changes

Phase 2 should make only changes justified by the specification.

Likely affected areas:

```text
app/
├── api/v1/endpoints/documents.py
├── db/repositories/documents.py
├── rag/
│   ├── chunking.py
│   └── normalization.py        # if introduced
├── integrations/storage/local.py
├── services/document_service.py
└── schemas/...                 # existing document schemas as needed

tests/
├── unit/
│   ├── test_chunking.py
│   └── test_normalization.py
└── integration/
    └── test_document_ingestion.py
```

Additional test files may be created when grouping by behavior improves readability.

The exact file list is not a requirement.

Implementation should follow existing repository conventions.

---

# 13. Expected Service Evolution

The existing:

```text
DocumentIngestionService
DocumentSearchService
```

should remain focused.

If listing and deletion introduce meaningful document-management workflows, a dedicated service may be introduced, conceptually:

```text
DocumentManagementService
```

However, avoid introducing this class merely because the name looks architecturally clean.

Create it when it owns actual orchestration such as:

```text
repository deletion
+
storage deletion
```

Deletion is a strong candidate because it crosses persistence boundaries.

---

# 14. Database Design

The existing primary relationship remains:

```text
documents
    |
    | 1
    |
    | *
document_chunks
```

Foreign key:

```text
document_chunks.document_id
    → documents.id
    ON DELETE CASCADE
```

Phase 2 should not change this relationship without a concrete requirement.

If no schema change is required:

```text
NO Alembic migration
```

If implementation introduces a schema change:

```text
create a NEW Alembic migration
```

Historical migrations must not be edited.

---

# 15. Storage Design

Current source storage remains local filesystem storage.

Conceptual interface needed for lifecycle management:

```text
save(...)
delete(...)
```

Deletion must operate only on known stored-document paths.

Phase 2 does not introduce:

- S3
- MinIO
- GCS
- distributed filesystem

Storage abstraction should remain simple enough that a future storage provider could replace local storage without changing API/business rules.

---

# 16. API Design

Existing operations remain:

```text
upload document
get document
search documents
```

Phase 2 may add:

```text
list documents
delete document
```

Exact URL conventions should follow the current `/api/v1` document router rather than creating a parallel API style.

Conceptually:

```text
GET    /documents
DELETE /documents/{document_id}
```

Existing single-document retrieval remains owner-scoped.

---

# 17. Error Mapping

Error responsibilities:

```text
Parser / Embedding / Storage
        ↓
Service
        ↓
domain/application behavior
        ↓
API
        ↓
HTTP response
```

Repository code should not generate HTTP exceptions.

Service code should not depend unnecessarily on FastAPI HTTP response objects.

API remains responsible for translating application outcomes into HTTP semantics.

---

# 18. Observability

Continue using structured/useful logging around document workflows.

Useful events include:

```text
document_ingested
document_ingestion_failed
document_deleted
```

Logs should include identifiers useful for debugging such as:

```text
document_id
owner_id
```

but must not log document contents unnecessarily.

Phase 2 does not require a new observability stack.

---

# 19. Implementation Order

Phase 2 should be implemented incrementally.

Recommended order:

```text
2.1 Document lifecycle tests
        ↓
2.2 Document deletion
        ↓
2.3 Document listing
        ↓
2.4 Text normalization
        ↓
2.5 Chunking improvements
        ↓
2.6 Retrieval filtering tests/improvements
        ↓
2.7 Retrieval result model
        ↓
2.8 Retrieval quality test completion
```

Each milestone should follow:

```text
Review spec/design
      ↓
Define behavior
      ↓
Write/update test
      ↓
Run test and observe failure where applicable
      ↓
Implement minimal change
      ↓
Run targeted tests
      ↓
Run full test suite
      ↓
Run Ruff
      ↓
Review diff
      ↓
Commit when explicitly approved
```

---

# 20. Validation Strategy

After each milestone:

```text
targeted pytest
```

After meaningful Phase 2 changes:

```text
full pytest
Ruff
format validation
```

Before Phase 2 merge:

- all unit tests pass
- all integration tests pass
- lint passes
- formatting passes
- migrations are valid if any were added
- Docker-based database integration tests work
- ownership constraints remain intact
- Phase 1 functionality has not regressed
- Spec and Detail Design match implementation

---

# 21. Design Constraints

The following rules apply throughout Phase 2:

1. Do not add LangChain without a demonstrated technical need.
2. Do not add agent frameworks.
3. Do not add background processing.
4. Do not add authentication as part of this phase.
5. Do not return SQLAlchemy models directly as API contracts.
6. Do not bypass owner scoping.
7. Do not modify historical Alembic migrations.
8. Do not add abstractions that merely wrap one function without meaningful responsibility.
9. Prefer deterministic tests.
10. Keep the retrieval subsystem independent from future LLM answer generation.

---

# 22. Phase 2 Target Architecture

At completion, the relevant architecture should conceptually be:

```text
                   FastAPI
                      |
          +-----------+-----------+
          |           |           |
        Upload       Manage      Search
          |           |           |
          v           v           v
     Ingestion     Document     Search
      Service      Management   Service
          |         Service       |
          |           |           |
          +-----------+-----------+
                      |
                      v
             DocumentRepository
                      |
                      v
              PostgreSQL/pgvector


Ingestion pipeline:

Source File
    |
    v
Parser
    |
    v
Extracted Text
    |
    v
Normalizer
    |
    v
Normalized Text
    |
    v
Chunker
    |
    v
Chunks
    |
    v
EmbeddingProvider
    |
    v
Vectors
    |
    v
DocumentRepository


Source-file lifecycle:

DocumentManagementService
          |
          +----> DocumentRepository
          |
          +----> LocalDocumentStorage
```

This architecture remains intentionally simple.

Phase 3 can then consume the stable retrieval layer to implement grounded LLM answer generation without requiring Phase 3 to solve document lifecycle and retrieval correctness again.