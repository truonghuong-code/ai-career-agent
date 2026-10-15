# Phase 4 — Detail design

## Components and interfaces

- `app/schemas/analysis.py`: strict extraction schemas `Evidence`, `ProfileFact`,
  `CVProfile`, `JDProfile`; request/response/provenance/source DTOs. Required fields
  with empty lists support structured JSON output without ambiguous optional facts.
- `app/services/analysis_prompt.py`: `build_analysis_prompt(kind, BuiltContext)`
  returns PromptMessage tuple. Domain instructions live here, outside generic RAG.
  User content is JSON-encoded source objects so embedded markers cannot create
  new structural sources; original text survives JSON decoding.
- `app/integrations/llm/analysis.py`: `AnalysisProvider.extract(messages, kind)`;
  fake returns empty profile (or controlled test profile); OpenAI wrapper calls
  shared `OpenAILLMProvider.generate_structured(messages, response_model)`.
  Existing QA `generate` remains backward compatible and uses the same transport.
- `app/db/models/analysis.py`: DocumentAnalysis, JSONB profile/sources/provenance,
  immutable application contract, unique (document_id, kind, version), positive
  version and kind/status checks; document foreign key ON DELETE CASCADE.
- `app/db/repositories/analyses.py`: `load_input(document_id, owner_id)`,
  `save(...)`, `get(id, owner)`, `list(document_id, owner, kind, limit, offset)`.
  Load scalar snapshots (not detached ORM) and release read transaction before LLM.
  Ordered chunks filter BOTH owners. Save locks owned document row, rechecks status
  and checksum, computes max(version)+1 and inserts atomically. Concurrent requests
  serialize only during save; no database lock held during LLM. All writers use
  this method; uniqueness is a second safeguard. Roll back on any save failure.
- `AnalysisService.create/get/list`: validate owner and inputs, load snapshot,
  ContextBuilder over ALL returned chunks, enforce context budget, build prompt,
  asyncio deadline, strict profile and exact-quote validation, persist response.
  Empty profiles yield insufficient_evidence; no-context is a rejected request.
- `app/api/v1/endpoints/analyses.py`: DI and HTTP error mapping only. Read routes
  do not instantiate a provider and remain available with generation misconfigured.

## Processing and data flow

Owned document → ordered chunk snapshots → ContextBuilder → domain prompt →
AnalysisProvider → strict profile → evidence checks → locked version allocation →
JSONB record → Pydantic response. No embeddings/retrieval ranking needed for extraction.
Only source IDs from server snapshots are persisted; provider supplies numbers/quotes.
Every stored context source can be inspected through full response. Prompt and schema
versions are `analysis-v1` / `1`; metadata records model/provider/output/timeout.
Generation reproducibility means retained inputs/configuration, not identical model output.

## Validation and security

Kinds are cv/jd. Strings and evidence arrays nonempty when a fact exists; no coercion
of booleans to source numbers. Exact quotes refer to normalized chunk text, not raw
PDF byte offsets. Validate every provider result again at service boundary, including
fake/substitute providers. Unsupported facts are not accepted without evidence.
Untrusted documents remain user data and cannot control system prompt/schema.
No content, quotes, profile, prompt, provider bodies or secrets in application logs.
Document deletion cascades snapshots as part of existing lifecycle semantics.

## Configuration and migration

Reuse LLM_PROVIDER, LLM_MODEL, LLM_TIMEOUT_SECONDS, OPENAI_API_KEY. Add
ANALYSIS_MAX_CONTEXT_CHARS=40000 and ANALYSIS_MAX_OUTPUT_TOKENS=4096, prefixed
AI_CAREER_AGENT_. Context budget includes encoded prompt data and formatted context;
reject entire input on overflow. These are character/output limits, not exact tokenizer budgets.
Migration `20261015_0003` creates document_analyses; downgrade removes only new table.
No modification of applied migrations or existing document_type/vector dimensions.

## Traceability

REQ-01/03/04 → schemas, prompt, evidence validator; REQ-02/08 → repositories/API;
REQ-05 → shared transport + providers/deadline; REQ-06/07 → model/migration/save;
REQ-09 → bounded context; NFR-01–04 → layering, offline fixtures, regression checks.
