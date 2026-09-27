# Roadmap

Roadmap này phân biệt rõ phần đã có trong repository và phần chỉ là kế hoạch. Thứ tự ưu tiên có thể thay đổi theo nhu cầu sản phẩm, nhưng các phase sau không nên vượt qua dependency kiến trúc của phase trước.

## Completed

### Phase 0 — Foundation

**Đã hoàn thành:** FastAPI app factory, health endpoint, Pydantic Settings, request-ID logging, SQLAlchemy async, Alembic, PostgreSQL + pgvector Docker Compose, pytest, Ruff và GitHub Actions CI.

### Phase 1 — Document ingestion và RAG foundation

**Đã hoàn thành:** upload PDF/DOCX/TXT/Markdown, local file storage, document/chunk metadata, parser registry, deterministic chunking, replaceable embedding provider, pgvector cosine retrieval, source metadata, ownership placeholder `X-Internal-User-ID`, migrations và integration tests.

## Planned

### Phase 2 — Retrieval quality và document lifecycle

**Objective:** làm retrieval đáng tin cậy hơn trước khi dùng nó làm context cho LLM.

**Major features:** đánh giá chunking với tài liệu thực tế; metadata/filtering phong phú hơn; document reprocessing/versioning hoặc deletion lifecycle; validation embedding dimension; retrieval evaluation dataset; có thể thêm keyword/hybrid search hoặc reranking nếu evaluation chứng minh cần thiết.

**Architecture considerations:** vẫn giữ parser/chunker/provider thay thế được; không thêm framework RAG lớn nếu implementation nhỏ hiện tại đáp ứng yêu cầu. Mọi filter phải giữ ownership scope.

**Dependencies:** Phase 1.

### Phase 3 — LLM integration và grounded answer generation

**Objective:** trả lời câu hỏi dựa trên retrieved chunks, với nguồn có thể truy vết.

**Major features:** LLM provider adapter, prompt/version management, structured answer schema, citations từ document/chunk, context assembly, error/cost/timeout handling và evaluation groundedness cơ bản.

**Architecture considerations:** retrieval vẫn là service độc lập; LLM layer không truy cập database trực tiếp. Chỉ đưa context đã scope theo owner vào prompt.

**Dependencies:** Phase 2 retrieval evaluation và metadata đủ tốt.

### Phase 4 — CV và JD analysis

**Objective:** chuyển CV và Job Description thành profile có cấu trúc, có evidence từ tài liệu nguồn.

**Major features:** document type conventions cho CV/JD, Pydantic schemas cho extracted profile, LLM structured output, persistence/versioning của analysis và source evidence.

**Architecture considerations:** đây là application workflow mới; không trộn logic CV/JD vào generic parser/retrieval. Thiết kế schema để có thể review và tái tạo analysis.

**Dependencies:** Phase 3 structured LLM output và grounded context.

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
