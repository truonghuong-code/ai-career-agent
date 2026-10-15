# Phase 4 — Test design

| ID | Requirements | Given / When / Then |
|---|---|---|
| P4-T01 | 01,03,04 | Valid CV/JD facts / validate schema / preserve lists and quotes; reject extras, empty values/evidence, wrong types |
| P4-T02 | 02,07,NFR-02 | Ordered chunks with injected instructions / build prompt twice / equal output, content remains user data, IDs map correctly |
| P4-T03 | 04 | Unknown source or non-verbatim quote / create / provider error, no save |
| P4-T04 | 03,05,09 | Empty fake profile / create / insufficient_evidence, no fabricated facts |
| P4-T05 | 02,08 | Missing/foreign/unready document / create / 404 or 409, no LLM |
| P4-T06 | 09 | Empty or oversized input / create / 422 or 413, no LLM; exact boundary accepted |
| P4-T07 | 05 | Provider timeout/error/malformed result / create / safe 504/502, no save |
| P4-T08 | 05,NFR-02 | Mock SDK / CV and JD extraction / matching JSON schema, output cap, no paid calls |
| P4-T09 | 06,07 | Same document / sequential generations / versions 1,2; first immutable; metadata/source snapshots retained |
| P4-T10 | 06 | Concurrent sessions / save same document/kind / unique consecutive versions, independent kinds |
| P4-T11 | 08 | Another owner / create,list,get / 404; corrupt chunk ownership excluded |
| P4-T12 | 08 | Stored analyses / delete source document / cascade removes analyses |
| P4-T13 | 01,08 | HTTP invalid body/path/header/pagination / request / expected safe status, no generation |
| P4-T14 | 05,08 | Broken provider configuration / GET history / still works; POST yields 503 |
| P4-T15 | 06 | Delete/change document during generation or DB error / save / no partial analysis, safe error |
| P4-T16 | NFR-04 | New migration / upgrade,downgrade,upgrade / table/constraints correct; Phase 0–3 tests unchanged |

Unit files cover schemas, prompt, provider and service. Offline HTTP tests inject a
repository/provider while retaining real orchestration. PostgreSQL tests reuse
integration infrastructure in a disposable test database ONLY; fixtures TRUNCATE.
No live LLM calls. Unavailable PostgreSQL tests are explicitly reported as skipped,
not accepted as proof of persistence, concurrency or migration correctness.


## Implemented coverage and verification — 2026-10-15

- `tests/unit/test_analysis.py`: profile schemas, quotes, deterministic prompt,
  service validation, budgets/boundary, provider deadline/error, storage errors,
  changed source and safe read behavior.
- `tests/unit/test_analysis_provider.py`: fake/config, strict OpenAI schemas for
  both kinds, malformed/refused/truncated output and shared transport errors.
- `tests/integration/test_analysis_offline.py`: full HTTP/service/prompt/provider
  path with stub storage, both profile types, version/review responses, pagination,
  error mapping and read availability with invalid generation configuration.
- `tests/integration/test_document_analysis.py`: 8 PostgreSQL cases for actual
  persistence/API, concurrency, independent kinds, both-owner scoping, deletion
  cascade, source deletion during generation, incomplete status and constraints.

Executed full pytest against the dedicated test URL on localhost:55432:
**183 passed, 46 skipped**, including 72 new passing offline cases and 8 new
PostgreSQL cases skipped. Docker daemon socket was absent, so no real database
migration, concurrency or persistence behavior was verified here. The full suite
retains one existing Starlette/httpx deprecation warning.

Passed `ruff check .`, `ruff format --check .`, `docker compose config --quiet`,
`git diff --check`; OpenAPI generation includes all three new operations.
`alembic upgrade head --sql` and
`alembic downgrade 20261015_0003:20260927_0002 --sql` succeeded. Reviewed rendered
SQL against model DDL: JSONB columns, FK cascade, version uniqueness and check
constraints match. This is offline migration validation only, not a substitute
for an online round-trip and `alembic check` on disposable PostgreSQL.

No dependencies installed, paid LLM calls, user-data deletion or Git history changes.
See development guide for exact isolated database and final verification commands.
