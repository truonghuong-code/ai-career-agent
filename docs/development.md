# Development guide

## Prerequisites

- Python 3.11 trở lên. Dockerfile và GitHub Actions dùng Python 3.12.
- Docker Desktop/Docker Engine có Docker Compose để chạy PostgreSQL + pgvector.
- Git.

## Python environment

Tạo virtual environment và cài dependency development theo `pyproject.toml`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
```

Khi dùng Windows, kích hoạt virtual environment bằng lệnh phù hợp shell của bạn. Không commit `.venv/`.

## Environment variables

Tạo file local từ mẫu:

```bash
cp .env.example .env
```

Application chỉ đọc settings có prefix `AI_CAREER_AGENT_`. Các biến hiện có:

| Variable | Default/example | Mục đích |
|---|---|---|
| `AI_CAREER_AGENT_APP_NAME` | `AI Career Agent` | Tên FastAPI application |
| `AI_CAREER_AGENT_ENVIRONMENT` | `local` | Nhãn môi trường |
| `AI_CAREER_AGENT_DEBUG` | `true` trong `.env.example` | FastAPI debug mode |
| `AI_CAREER_AGENT_LOG_LEVEL` | `INFO` | Mức logging |
| `AI_CAREER_AGENT_DATABASE_URL` | asyncpg PostgreSQL URL | Kết nối database |
| `AI_CAREER_AGENT_DOCUMENT_STORAGE_DIR` | `uploads` | Directory lưu file gốc |
| `AI_CAREER_AGENT_MAX_UPLOAD_SIZE_BYTES` | `10485760` | Giới hạn upload 10 MiB |
| `AI_CAREER_AGENT_EMBEDDING_PROVIDER` | `deterministic` | `deterministic` hoặc `openai` |
| `AI_CAREER_AGENT_EMBEDDING_MODEL` | `text-embedding-3-small` | Model OpenAI khi provider là `openai` |
| `AI_CAREER_AGENT_EMBEDDING_DIMENSIONS` | `256` | Phải giữ 256 vì schema vector hiện tại |
| `AI_CAREER_AGENT_OPENAI_API_KEY` | rỗng | Chỉ cần khi provider là `openai` |

Docker Compose cũng dùng `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` để khởi tạo container database. `.env` chứa mật khẩu/key local và bị `.gitignore`; không đưa secret thật vào `.env.example`.

## Docker Compose và PostgreSQL/pgvector

Khởi động riêng database cho local development:

```bash
docker compose up -d db
```

Compose dùng image `pgvector/pgvector:pg16`, port host `5432`, health check `pg_isready`, và named volume `postgres_data`. API container dùng volume `document_uploads` cho raw uploads.

Chạy cả API và database bằng Docker:

```bash
docker compose up --build
```

API chạy ở `http://localhost:8000`; OpenAPI UI ở `/docs`.

Kiểm tra compose syntax/rendered configuration mà không start container:

```bash
docker compose config --quiet
```

## Alembic migrations

Sau khi database đã healthy, áp dụng migration:

```bash
alembic upgrade head
```

Khi API đang chạy trong Docker, chạy migration từ API image:

```bash
docker compose run --rm api alembic upgrade head
```

Migration hiện tại bật pgvector và tạo `documents`, `document_chunks`, cùng HNSW cosine index. Với thay đổi schema mới, tạo migration Alembic mới; không sửa migration lịch sử đã được áp dụng.

Có thể render migration SQL offline để kiểm tra cấu trúc mà không kết nối database:

```bash
alembic upgrade head --sql
```

Offline SQL không thay thế việc chạy `alembic upgrade head` với PostgreSQL thật.

## Run FastAPI locally

```bash
uvicorn app.main:app --reload
```

Health check:

```bash
curl http://localhost:8000/api/v1/health
```

Document endpoint yêu cầu placeholder header:

```bash
curl -X POST http://localhost:8000/api/v1/documents \
  -H "X-Internal-User-ID: local-user" \
  -F "file=@example.txt"
```

Header này chưa phải authentication. Nó chỉ scope document query trong Phase 1.

## Tests, lint và formatting

Chạy toàn bộ suite:

```bash
pytest
```

Unit tests không cần database. Integration tests cần PostgreSQL + pgvector đã chạy và migration đã áp dụng. Nếu database không available, fixture hiện tại skip integration tests; CI luôn chạy chúng với PostgreSQL service.

Chạy checks:

```bash
ruff check .
ruff format --check .
```

Ruff format có thể áp dụng formatting:

```bash
ruff format .
```

Trước khi handoff, kiểm tra whitespace trong diff:

```bash
git diff --check
```

## CI expectations

Workflow `.github/workflows/ci.yml` chạy trên Python 3.12, provision service `pgvector/pgvector:pg16`, cài `.[dev]`, chạy Ruff, `alembic upgrade head`, rồi `pytest`. Code thay đổi database phải pass migration và integration test trong CI.

## Common troubleshooting

### Docker daemon không chạy

Nếu `docker compose up -d db` báo không kết nối được Docker socket, khởi động Docker Desktop/Docker Engine rồi chạy lại. `docker compose config --quiet` chỉ validate configuration, không chứng minh daemon/database đang chạy.

### Integration tests bị skip hoặc connection refused

Khởi động database và migration:

```bash
docker compose up -d db
alembic upgrade head
pytest
```

Kiểm tra `.env` có database URL host `localhost:5432`; URL bên trong Compose API dùng hostname `db`.

### Lỗi OpenAI embedding

Đặt `AI_CAREER_AGENT_EMBEDDING_PROVIDER=openai`, cung cấp `AI_CAREER_AGENT_OPENAI_API_KEY`, và giữ `AI_CAREER_AGENT_EMBEDDING_DIMENSIONS=256`. Nếu không cần embedding provider thật khi local, dùng default `deterministic`.

### Lỗi pgvector dimension

`document_chunks.embedding` hiện là `vector(256)`. Không đổi dimension environment để khắc phục; tạo migration, cập nhật model và provider cùng nhau.

### Upload không được nhận

Endpoint chỉ hỗ trợ PDF, DOCX, TXT và Markdown; text phải UTF-8. Kiểm tra file không rỗng, nhỏ hơn upload limit, và header `X-Internal-User-ID` có mặt.
