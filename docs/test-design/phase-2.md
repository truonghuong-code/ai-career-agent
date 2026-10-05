# Phase 2 — Retrieval Quality & Document Lifecycle Test Design

## 1. Purpose

This document defines the test design for Phase 2 — Retrieval Quality & Document Lifecycle.

The purpose of these tests is to verify that the implementation satisfies the requirements defined in:

- `docs/specs/phase-2.md`
- `docs/design/phase-2.md`

Each test case should be traceable to a Phase 2 requirement and should later be implemented as an automated test under the `tests/` directory.

---

## 2. Test Strategy

Phase 2 uses a combination of:

- **Unit tests** for isolated logic such as normalization, chunking, and storage behavior.
- **Integration tests** for repository, PostgreSQL, pgvector, ownership, document lifecycle, and cascade deletion.
- **API tests** for HTTP behavior, request validation, response status codes, and ownership isolation.

Tests should verify both successful behavior and failure behavior.

---

# 3. Phase 2.2 — Document Deletion

## 3.1 Test Scope

Document deletion tests verify that:

- only the document owner can delete a document
- the document is removed from PostgreSQL
- associated `DocumentChunk` records are removed through cascade deletion
- the source file is removed from local storage
- deleting a non-existing document is handled safely
- an already-missing source file does not prevent database cleanup
- storage paths outside the configured storage directory are rejected
- unexpected filesystem errors are not silently ignored
- the DELETE API returns the correct HTTP status codes

---

## 3.2 Test Cases

| ID | Level | Test Case | Expected Result |
|---|---|---|---|
| DD-001 | Integration | Owner deletes an existing document | Deletion succeeds and returns `True` |
| DD-002 | Integration | Delete a document containing chunks | All associated chunks are removed |
| DD-003 | Integration | Delete a document with an existing source file | Source file is removed |
| DD-004 | Integration | Another owner attempts to delete the document | Deletion returns `False`; document, chunks, and file remain |
| DD-005 | Integration | Delete a non-existing document | Deletion returns `False` |
| DD-006 | Integration | Source file is already missing | Database deletion still succeeds |
| DD-007 | Unit | Storage path escapes configured storage directory | Deletion is rejected |
| DD-008 | Unit | Unexpected filesystem deletion error occurs | Exception is propagated |
| DD-009 | API | Owner deletes an existing document through API | HTTP `204 No Content` |
| DD-010 | API | Document is not found or belongs to another owner | HTTP `404 Not Found` |

---

## 3.3 Detailed Test Cases

### DD-001 — Delete Owned Document

**Level:** Integration

**Purpose:**  
Verify that a document owner can delete an existing document.

**Preconditions:**

- A document exists in the database.
- The document belongs to `owner-1`.

**Action:**

Call:

`DocumentManagementService.delete_document(document_id, "owner-1")`

**Expected Result:**

- The method returns `True`.
- The document no longer exists in the database.

---

### DD-002 — Cascade Delete Document Chunks

**Level:** Integration

**Purpose:**  
Verify that deleting a document also deletes all associated chunks through the existing database cascade behavior.

**Preconditions:**

- A document exists.
- The document has one or more `DocumentChunk` records.

**Action:**

Delete the document through `DocumentManagementService`.

**Expected Result:**

- The document is deleted.
- No `DocumentChunk` remains for the deleted `document_id`.

**Requirement Verified:**

The existing `ON DELETE CASCADE` relationship works correctly.

---

### DD-003 — Delete Source File

**Level:** Integration

**Purpose:**  
Verify that successful document deletion also removes the source file from local storage.

**Preconditions:**

- A document exists.
- Its `storage_path` points to an existing file inside the configured storage directory.

**Action:**

Delete the document.

**Expected Result:**

- Database deletion succeeds.
- The source file no longer exists.

---

### DD-004 — Ownership Isolation

**Level:** Integration

**Purpose:**  
Verify that one owner cannot delete another owner's document.

**Preconditions:**

- A document belongs to `owner-1`.
- The deletion request uses `owner-2`.

**Action:**

Call:

`DocumentManagementService.delete_document(document_id, "owner-2")`

**Expected Result:**

- The method returns `False`.
- The document remains in the database.
- Associated chunks remain.
- The source file remains.

**Security Property:**

Document deletion must always be owner-scoped.

---

### DD-005 — Delete Non-existing Document

**Level:** Integration

**Purpose:**  
Verify safe behavior when the requested document does not exist.

**Preconditions:**

- The requested `document_id` does not exist.

**Action:**

Attempt to delete the document.

**Expected Result:**

- The service returns `False`.
- No unrelated database records are modified.
- No storage file is deleted.

---

### DD-006 — Source File Already Missing

**Level:** Integration

**Purpose:**  
Verify that an already-missing source file does not prevent database cleanup.

**Preconditions:**

- The document exists in the database.
- The source file does not exist.

**Action:**

Delete the document.

**Expected Result:**

- The service returns `True`.
- The document is removed from the database.
- Associated chunks are removed.
- No filesystem exception is raised because the source file is already absent.

---

### DD-007 — Reject Storage Path Outside Base Directory

**Level:** Unit

**Purpose:**  
Verify that `LocalDocumentStorage.delete()` cannot delete files outside the configured storage directory.

**Preconditions:**

Configured storage directory:

`/app/uploads`

A malicious or invalid storage path attempts to escape that directory, for example:

`../../important.txt`

**Action:**

Call `LocalDocumentStorage.delete()` with the invalid path.

**Expected Result:**

- The resolved path is detected as being outside `base_dir`.
- The operation raises an exception.
- The external file is not deleted.

**Security Property:**

Filesystem deletion must be constrained to the configured document storage directory.

---

### DD-008 — Unexpected Filesystem Failure

**Level:** Unit

**Purpose:**  
Verify that unexpected filesystem failures are not silently converted into successful deletion.

**Preconditions:**

- Database deletion succeeds.
- Source file deletion raises an unexpected filesystem exception such as `PermissionError` or `OSError`.

**Action:**

Execute document deletion.

**Expected Result:**

- The filesystem exception is propagated.
- The error is not silently converted into `False` or `True`.

**Known Limitation:**

PostgreSQL and the local filesystem do not share one transaction. Because the current design deletes the database record before deleting the source file, a filesystem failure may leave an orphan source file.

Phase 2.2 does not introduce distributed transaction or compensation logic for this case.

---

### DD-009 — DELETE API Success

**Level:** API

**Purpose:**  
Verify successful HTTP deletion behavior.

**Preconditions:**

- The requested document exists.
- The request owner owns the document.

**Action:**

Send:

`DELETE /documents/{document_id}`

**Expected Result:**

- HTTP status is `204 No Content`.
- Response body is empty.
- Document deletion is completed.

---

### DD-010 — DELETE API Not Found

**Level:** API

**Purpose:**  
Verify that the API does not reveal whether a document exists for another owner.

**Preconditions:**

Either:

- the document does not exist, or
- the document belongs to another owner.

**Action:**

Send:

`DELETE /documents/{document_id}`

**Expected Result:**

- HTTP status is `404 Not Found`.
- Response contains the configured not-found error.
- No document belonging to another owner is modified.

---

## 3.4 Traceability

| Requirement | Design Component | Test Cases |
|---|---|---|
| Owner can delete own document | `DocumentManagementService` + `DocumentRepository` | DD-001 |
| Chunks deleted with document | PostgreSQL `ON DELETE CASCADE` | DD-002 |
| Source file removed | `LocalDocumentStorage.delete()` | DD-003 |
| Ownership isolation | Owner-scoped repository operations | DD-004, DD-010 |
| Missing document handled safely | Service + API | DD-005, DD-010 |
| Missing file tolerated | `LocalDocumentStorage.delete()` | DD-006 |
| Storage path constrained | `LocalDocumentStorage.delete()` | DD-007 |
| Filesystem errors surfaced | Service + Storage | DD-008 |
| HTTP success contract | DELETE endpoint | DD-009 |
| HTTP not-found contract | DELETE endpoint | DD-010 |

---

## 3.5 Exit Criteria

Phase 2.2 document deletion testing is complete when:

- DD-001 through DD-010 are implemented.
- All tests pass.
- Existing Phase 1 and Phase 2.1 tests continue to pass.
- Ruff passes.
- No ownership isolation regression is introduced.
- No document chunks remain after successful document deletion.

---

# 4. Phase 2.3 — Document Listing

## 4.1 Test Scope

Document listing tests verify that the management API returns only documents
owned by the current internal user, includes management metadata for every
processing status, and uses a deterministic order.

## 4.2 Test Cases

| ID | Level | Test Case | Expected Result |
|---|---|---|---|
| DL-001 | Integration | List documents for one owner | Only that owner's documents are returned, including processing, completed, and failed states. |
| DL-002 | Integration | List ordering | Results are ordered by `created_at DESC`, then `id DESC`. |
| DL-003 | API | List documents through HTTP | `GET /documents` returns `200` and the documented metadata schema. |
| DL-004 | API | Owner isolation through HTTP | A caller cannot receive another owner's documents. |

## 4.3 Detailed Test Cases

### DL-001 — Owner-scoped status-inclusive listing

Create documents for two owners and ensure the selected owner receives only
their own documents. The response must include documents in `PROCESSING`,
`COMPLETED`, and `FAILED` states because listing is a management operation.

### DL-002 — Deterministic listing order

Create documents with distinct `created_at` values and verify that the newest
document is returned first. The repository query must use `id DESC` as a
secondary ordering key.

### DL-003 — List API metadata contract

Call `GET /api/v1/documents` with `X-Internal-User-ID`. Verify HTTP `200` and
the returned document metadata: ID, filename, MIME type, document type, size,
checksum, processing status, extracted text length, error information, and
timestamps.

### DL-004 — List API ownership isolation

Create documents for separate owners, call the endpoint for one owner, and
verify that the other owner's IDs and filenames are absent.

---

# 5. Phase 2.4 — Text Normalization

## 5.1 Test Scope

Normalization tests verify a conservative deterministic transformation between
parser extraction and chunking. They must preserve paragraph boundaries and
must not change the `extracted_text_length` contract, which remains the length
of raw extracted text.

## 5.2 Test Cases

| ID | Level | Test Case | Expected Result |
|---|---|---|---|
| TN-001 | Unit | Normalize line endings | CRLF and CR become LF. |
| TN-002 | Unit | Trim and bound blank lines | Outer whitespace is removed; three or more line breaks become one paragraph break. |
| TN-003 | Unit | Deterministic normalization | Equivalent repeated calls produce identical output and preserve meaningful internal whitespace. |
| TN-004 | Integration | Ingestion chunks normalized text | Stored chunk text is derived from normalized parser output while extracted text length remains raw length. |
| TN-005 | Integration | Whitespace-only extracted text | Ingestion completes predictably with no chunks and the raw extracted text length retained. |

## 5.3 Detailed Test Cases

### TN-001 through TN-003 — Normalizer behavior

Use unit tests for line-ending conversion, bounded blank lines, outer trimming,
determinism, and preservation of non-line-break internal whitespace.

### TN-004 — Normalization placement in ingestion

Ingest text containing CRLFs and excessive blank lines. Verify persisted chunk
text reflects normalized text and that `extracted_text_length` equals the raw
extracted text length rather than normalized length.

### TN-005 — Empty normalized content

Ingest whitespace-only text. Verify the document is marked `COMPLETED`, stores
the raw extracted text length, and has no chunk rows. This documents the
existing empty-content behavior without adding a new validation rule.

---

# 6. Phase 2.5 — Chunking Improvements

## 6.1 Test Scope

Chunking tests verify deterministic chunks derived directly from normalized
text. They verify stable indexes, valid offsets, non-empty chunk text, bounded
chunk size, structure preservation, overlap progress, and configuration
validation.

## 6.2 Test Cases

| ID | Level | Test Case | Expected Result |
|---|---|---|---|
| CI-001 | Unit | Determinism, offsets, and chunk metadata | Equal input/configuration produces equal ordered chunks; each chunk has a sequential index, non-empty text, valid offsets, and text equal to its source slice. |
| CI-002 | Unit | Preserve normalized paragraph structure | A chunk that contains the full normalized input retains line and paragraph boundaries. |
| CI-003 | Unit | High valid overlap progress | A valid overlap close to chunk size advances the end boundary on every chunk and terminates. |
| CI-004 | Unit | Reject invalid chunk configuration | Zero chunk size, negative overlap, and overlap greater than or equal to chunk size raise `ValueError`. |
| CI-005 | Integration | Ingestion persists structure-preserving chunk text | A normalized document is persisted with paragraph boundaries in its chunk text; raw extracted length remains unchanged. |

## 6.3 Detailed Test Cases

### CI-001 — Deterministic chunks and source-consistent offsets

Run `split()` twice with the same normalized text and configuration. Verify
identical chunks, indexes beginning at zero, non-empty text, valid offsets,
and `text[char_start:char_end] == chunk.text` for every chunk.

### CI-002 — Preserve normalized structure

Use a normalized heading and paragraphs that fit in one chunk. Verify the
chunk retains `\n` and `\n\n`; the chunker must not perform a second global
whitespace normalization.

### CI-003 — Overlap forward progress

Use a long unbroken token with `chunk_overlap = chunk_size - 1`. Verify each
successive chunk has a strictly greater end offset and chunking terminates.

### CI-004 — Invalid configuration

Verify configurations that cannot make meaningful progress are rejected at
construction time.

### CI-005 — Ingestion integration

The Phase 2.4 normalization ingestion test also verifies this pipeline
property: persisted chunk text retains normalized paragraph boundaries while
`extracted_text_length` remains the raw parser output length.
