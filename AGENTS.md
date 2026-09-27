# Hướng dẫn cho coding agents

## Mục đích dự án

AI Career Agent là backend Python cho một ứng dụng hỗ trợ phát triển nghề nghiệp theo hướng AI Engineer và BrSE. Hiện tại dự án mới triển khai nền tảng và Phase 1: tiếp nhận tài liệu, trích xuất text, chunking xác định, embedding thay thế được, và tìm kiếm vector. Không có AI Agent hay logic tư vấn nghề nghiệp trong code hiện tại.

## Công nghệ hiện tại

- Python 3.11+ (CI và Docker dùng Python 3.12)
- FastAPI, Pydantic Settings, Uvicorn
- SQLAlchemy async + asyncpg
- PostgreSQL 16 + pgvector
- Alembic
- `pypdf`, `python-docx`, `python-multipart`
- OpenAI SDK cho provider embedding tùy chọn
- pytest, pytest-asyncio, Ruff
- Docker Compose và GitHub Actions

## Nguyên tắc kiến trúc

- Giữ các layer rõ ràng: `api` → `services` → `repositories` → database.
- API route chỉ xử lý HTTP, dependency và chuyển đổi lỗi; không đặt orchestration nghiệp vụ hay SQL trong route.
- Pydantic schemas là hợp đồng request/response; SQLAlchemy models không được trả trực tiếp từ API.
- Services điều phối workflow; repositories là nơi truy cập dữ liệu.
- Các integration có khả năng thay thế phải có interface nhỏ, rõ ràng: parser registry, embedding provider, storage adapter.
- Ưu tiên Python rõ ràng, typed và ít abstraction. Không tự ý thêm LangChain; chỉ dùng khi có lý do kỹ thuật được ghi trong tài liệu/PR/task.
- Không triển khai feature tương lai (Agent, CV/JD analysis, RAG answer generation, auth…) nếu task không yêu cầu.

## Quy tắc theo trách nhiệm

- `app/api/`: router, endpoint, HTTP status, dependency injection.
- `app/schemas/`: Pydantic request/response schema.
- `app/services/`: workflow/use case, logging nghiệp vụ và mapping lỗi domain.
- `app/db/models/`: SQLAlchemy models.
- `app/db/repositories/`: query, persistence và ownership filtering.
- `app/rag/`: parser, chunker, embedding provider và retrieval primitives.
- `app/integrations/`: adapter ra dịch vụ/provider/storage bên ngoài.
- `app/core/`: configuration, logging, middleware và concern dùng chung.

## Database và migration

- Dùng SQLAlchemy async; không truy cập database bằng SQL raw trong service/route trừ khi repository/migration có lý do rõ ràng.
- Mọi model/schema change phải có Alembic migration mới trong `migrations/versions/`; không sửa migration đã được áp dụng.
- Migration phải có `upgrade()` và `downgrade()` hợp lý, và phải được kiểm tra bằng `alembic upgrade head` với PostgreSQL/pgvector khi có thể.
- `document_chunks.embedding` hiện là `vector(256)`. Không đổi dimension chỉ bằng environment variable; cần migration, cập nhật model và provider cùng lúc.
- Luôn scope document/chunk query theo ownership. Hiện tại dùng `owner_id` từ `X-Internal-User-ID`; đây chưa phải authentication.

## API, logging và lỗi

- Endpoint mới nằm dưới `/api/v1` và dùng response schema rõ ràng.
- Bảo toàn quy ước request ID: middleware trả `X-Request-ID` và log request completion.
- Dùng lỗi tường minh, HTTP status phù hợp và không để lộ secret/stack trace cho client.
- Log các sự kiện nghiệp vụ quan trọng với ID an toàn để trace; không log document content, API key hay credential.
- Không thay đổi health check trừ khi task yêu cầu.

## Configuration và security

- Tất cả application setting dùng tiền tố `AI_CAREER_AGENT_`, được định nghĩa trong `app/core/config.py` và minh họa trong `.env.example`.
- Không commit `.env`, API key, password thật, upload thật, database dump hay log có dữ liệu nhạy cảm.
- Khi thêm setting, cập nhật `Settings`, `.env.example`, Docker Compose nếu cần, README/development docs và test liên quan.
- `X-Internal-User-ID` chỉ là placeholder phát triển; không mô tả nó như một cơ chế bảo mật production.

## Dependencies và Git

- Chỉ thêm dependency khi cần thiết cho task; ưu tiên standard library hoặc dependency hiện có.
- Cập nhật `pyproject.toml` và tài liệu khi dependency thay đổi. Không thêm framework lớn chỉ để rút ngắn vài dòng code.
- Giữ diff nhỏ, không sửa format/code không liên quan.
- Không commit, amend, force-push hoặc push trừ khi người dùng yêu cầu rõ ràng.

## Workflow bắt buộc cho mọi implementation task

1. Inspect code và tài liệu liên quan.
2. Hiểu kiến trúc hiện có và các giới hạn của phase hiện tại.
3. Xác định file bị ảnh hưởng.
4. Lập kế hoạch ngắn.
5. Implement giải pháp nhỏ nhất nhưng sạch.
6. Chạy test liên quan.
7. Chạy full test suite: `pytest`.
8. Chạy `ruff check .`.
9. Chạy `ruff format --check .`.
10. Chạy `docker compose config --quiet` nếu Docker Compose liên quan hoặc có thể bị ảnh hưởng.
11. Chạy Alembic validation khi database/migration thay đổi; ưu tiên `alembic upgrade head` với database thật, hoặc ghi rõ nếu chỉ kiểm tra offline được.
12. Chạy `git diff --check`.
13. Review final diff, bỏ thay đổi không cần thiết.
14. Sửa mọi issue phát hiện được.
15. Báo cáo bằng tiếng Việt: thay đổi, file thay đổi, test đã chạy, kết quả validation, giới hạn còn lại và quyết định kiến trúc.

Nếu integration tests cần PostgreSQL nhưng database chưa chạy, không được báo là đã xác minh đầy đủ. Hãy nói rõ test nào bị skip/blocked và command cần thiết để chạy chúng.
