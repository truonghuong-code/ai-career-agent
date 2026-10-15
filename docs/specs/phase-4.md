# Phase 4 — CV / Job Description analysis specification

## Purpose and scope

Implement the roadmap's CV/JD structured extraction, evidence, persistence and
versioning. No approved Phase 4 detail existed; the following minimal contracts
specialize the roadmap without adding Phase 5 scoring or recommendations.
Dependencies: Phase 1 ingestion/chunks, Phase 2 ownership/lifecycle, Phase 3
context formatting, prompt messages and structured OpenAI transport.

## Requirements

| ID | Requirement |
|---|---|
| P4-REQ-01 | Explicit `kind=cv|jd` on analysis creation; existing document_type stays file format (pdf/docx/txt/markdown). No implicit classification or ingestion contract change. |
| P4-REQ-02 | Only owned, completed documents may be analyzed. Load all owned chunks in chunk_index order; do not use similarity top-k for full-document extraction. |
| P4-REQ-03 | CV profile: headline, skills, experience, education, certifications, languages. JD profile: title, employer, required_skills, preferred_skills, responsibilities, qualifications, languages. Each field is a list of evidenced facts. |
| P4-REQ-04 | Every fact has nonblank value and one or more evidence references: source_number and exact nonblank quote. Numbers must map to supplied chunks and quotes must occur verbatim there. Unknown fields/types/unsupported references fail. |
| P4-REQ-05 | Async replaceable extraction provider, offline fake, OpenAI structured output reusing Phase 3 transport. Timeout, refusal, empty/malformed output and infrastructure failures are explicit. |
| P4-REQ-06 | Append-only successful analyses with monotonically increasing version per document/kind, unique even under concurrency. Empty profiles are persisted as insufficient_evidence; failures persist nothing. |
| P4-REQ-07 | Persist source snapshots (IDs/index/text), document checksum, profile, kind, schema/prompt versions, actual prompt messages, provider/model and generation limits. History can be reviewed and input reconstructed; live output need not be deterministic. |
| P4-REQ-08 | Owner-scoped create/list/get APIs and deletion cascade when the source document is deleted. Cross-owner IDs behave as not found. |
| P4-REQ-09 | Reject no usable text and over-budget context before calling provider; never silently truncate. Missing facts are empty arrays, never inferred experience durations/proficiency. |

## Inputs, outputs and business rules

- POST `/api/v1/documents/{document_id}/analyses`, body `{"kind":"cv"}` or `jd`;
  returns 201 with a stored analysis. Repeating POST intentionally creates a new version.
- GET same path lists metadata (newest first), optional kind, limit 1–100 (20 default),
  offset >=0. GET `/api/v1/analyses/{analysis_id}` returns full profile/evidence/snapshots.
- Required temporary `X-Internal-User-ID`; this is not production authentication.
- Output contains id, document_id, kind, version, status (`completed` or
  `insufficient_evidence`), checksum, profile, sources, provenance and created_at.
- Do not infer personal attributes, suitability, seniority or skill scores.
  Empty lists mean “not extracted”, not “candidate lacks this skill”.
- Evidence validation establishes source traceability, not semantic entailment.
  Results remain model-assisted extracts for review.

## Errors

400 missing owner; 422 invalid input; 404 missing/foreign document or analysis;
409 document not completed or changed/deleted during generation; 422 no usable text;
413 context beyond configured character budget; 502 provider/invalid evidence;
504 timeout; 503 configuration or database failure. No raw exceptions/PII in logs.
Invalid generations do not create partial records or consume version numbers.

## Non-functional requirements

P4-NFR-01: typed async API → service → repository; no SDK/SQL in HTTP/business flow.
P4-NFR-02: deterministic context/prompt/fake output, independently testable offline.
P4-NFR-03: ownership filters for document/chunks/analysis, safe logs, bounded context/output.
P4-NFR-04: Phase 0–3 compatibility, no embedding dimension or historical migration changes.

## Acceptance and exclusions

Both CV and JD can be extracted, validated, persisted, listed and fetched with
source evidence; repeated and concurrent requests preserve immutable history;
foreign access fails; deleting a document removes its analyses. Unit, offline HTTP
and real PostgreSQL tests cover these rules, and migrations support upgrade/downgrade.
Real DB verification must be reported separately if unavailable.

Excluded: skill-gap matching, scoring, learning plans, agents, automatic document
classification, profile editing, auth, OCR, streaming, background jobs and fine-tuning.
