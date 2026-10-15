# Roadmap

Roadmap này phân biệt rõ phần đã có trong repository và phần chỉ là kế hoạch. Thứ tự ưu tiên có thể thay đổi theo nhu cầu sản phẩm, nhưng các phase sau không nên vượt qua dependency kiến trúc của phase trước.

## Completed

### Phase 0 — Foundation

**Đã hoàn thành:** FastAPI app factory, health endpoint, Pydantic Settings, request-ID logging, SQLAlchemy async, Alembic, PostgreSQL + pgvector Docker Compose, pytest, Ruff và GitHub Actions CI.

### Phase 1 — Document ingestion và RAG foundation

**Đã hoàn thành:** upload PDF/DOCX/TXT/Markdown, local file storage, document/chunk metadata, parser registry, deterministic chunking, replaceable embedding provider, pgvector cosine retrieval, source metadata, ownership placeholder `X-Internal-User-ID`, migrations và integration tests.

### Phase 2 — Retrieval quality và document lifecycle

**Đã hoàn thành:** document lifecycle `processing → completed/failed`,
owner-scoped document listing/deletion, database cascade và local-file cleanup,
deterministic text normalization/chunking, retrieval filtering theo owner/status/
document IDs/limit, stable retrieval result contract và integration quality tests
với deterministic embeddings. Phase này vẫn dùng `X-Internal-User-ID` như
ownership placeholder, chưa phải authentication.

### Phase 3 — LLM integration và grounded answer generation

**Đã triển khai:** ContextBuilder, PromptBuilder, async LLM protocol, offline fake
provider, OpenAI adapter với structured response, GroundedQAService và
`POST /api/v1/qa`. Có citation validation, owner-scoped retrieval, no-context /
insufficient-evidence status, timeout và safe error mapping; unit/API/integration tests.
Fake provider chỉ là stub offline. Live model quality, prompt-injection evaluation,
token-budget optimization và cost telemetry chưa thuộc phần đã xác minh.

## Implemented — verification pending

### Phase 4 — CV và JD analysis

**Đã triển khai:** CV/JD extraction workflow trên tài liệu đã ingest; Pydantic
profiles có evidence quotes; provider fake/OpenAI; create/list/get APIs;
persistence và append-only versions; source/prompt/config snapshots; owner filtering,
context budget và cascade lifecycle. Migration mới `20261015_0003`.

**Verification:** unit và offline HTTP tests chạy không cần LLM trả phí. PostgreSQL
integration/concurrency và migration online cần database test riêng; xem kết quả
thực thi trong `docs/test-design/phase-4.md`. Chưa coi là đã xác minh đầy đủ khi
các kiểm tra PostgreSQL chưa chạy.

**Giới hạn:** fake trả empty profile; quote checks không chứng minh semantic
entailment. Không có scoring, skill-gap hay learning plan (Phase 5).

## Planned

### Phase 5 — Skill gap và personalized learning plan

**Objective:** so sánh profile CV với yêu cầu JD và sinh kế hoạch học cá nhân hóa.

**Major features:** skill taxonomy ban đầu cho AI Engineer/BrSE, matching có explainability, missing/matched skills, mục tiêu/thời lượng học và learning plan có milestones.

**Architecture considerations:** định nghĩa deterministic business rules ở service trước; dùng LLM cho synthesis/explanation thay vì để LLM là nguồn duy nhất của score. Lưu input/version/evidence để audit kết quả.

**Dependencies:** Phase 4.

### Phase 6 — Authentication và user isolation

**Objective:** thay placeholder ownership bằng danh tính và authorization thật.

**Major features:** users/workspaces, authentication, authorization dependency, ownership migration/backfill, secure file access, rate limits và audit baseline.

**Architecture considerations:** thay `X-Internal-User-ID` bằng identity đã xác thực mà không phá repository ownership filter. Xem lại existing document data trước khi migration.

**Dependencies:** có thể bắt đầu sớm hơn nếu sản phẩm cần multi-user; bắt buộc trước public deployment.

### Phase 7 — Agentic AI orchestration

**Objective:** điều phối tools/workflows có state một cách có kiểm soát.

**Major features:** career orchestration layer, explicit tool contracts, run state, structured tool output, trace per run/tool, guardrails và evaluation scenarios.

**Architecture considerations:** bắt đầu bằng orchestration Python nhỏ trong `app/agents/` và tái sử dụng service hiện có. Chỉ đưa LangGraph/PydanticAI/OpenAI Agents SDK vào sau khi branching/state complexity được chứng minh; không dùng autonomous multi-agent mặc định.

**Dependencies:** Phase 3–5; Phase 6 nếu agent chạy trên dữ liệu người dùng thật.

### Phase 8 — Interview practice

**Objective:** cho phép session phỏng vấn dựa trên CV/JD và đánh giá theo từng turn.

**Major features:** interview session/turn persistence, question generation, rubric có cấu trúc, answer evaluation, feedback và adaptive follow-up.

**Architecture considerations:** state session nằm trong database, không chỉ prompt history; cần đánh giá chất lượng/consistency trước khi public.

**Dependencies:** Phase 4, Phase 5 và LLM integration; Phase 6 cho user data thật.

### Phase 9 — Japanese IT communication coaching

**Objective:** luyện giao tiếp tiếng Nhật trong bối cảnh IT/BrSE.

**Major features:** role-play meeting, requirement clarification, progress report và client communication; feedback ngữ pháp/keigo/IT vocabulary; material retrieval; tracking lỗi lặp lại.

**Architecture considerations:** tách scenario/rubric/learning material khỏi generic interview logic; đánh giá tiếng Nhật cần dataset và human review criteria.

**Dependencies:** Phase 3 retrieval + LLM integration, Phase 6 identity, có thể tái sử dụng agent/session primitives từ Phase 7–8.

### Phase 10 — Production hardening, observability và deployment

**Objective:** vận hành an toàn, đo lường được và có thể mở rộng.

**Major features:** background worker/queue cho ingestion nặng, cloud object storage, migrations/deploy CI-CD, backup/recovery, OpenTelemetry/tracing, metrics, structured logs, LLM cost tracking, RAG/agent evaluation, security review và performance/load testing.

**Architecture considerations:** chỉ chọn managed service hoặc distributed component khi load/reliability data chứng minh cần thiết. Database migration, storage lifecycle và PII retention phải được thiết kế cùng nhau.

**Dependencies:** ít nhất Phase 6; các phần khác triển khai dần theo feature được public.
