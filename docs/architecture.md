# Kiến trúc hiện tại

## Phạm vi đã triển khai

Hệ thống hiện là FastAPI backend với một workflow hoàn chỉnh cho document ingestion và vector retrieval. Nó nhận PDF, DOCX, TXT hoặc Markdown, lưu file gốc trên local filesystem, trích xuất text, tạo chunk xác định, sinh embedding, và lưu metadata/chunk/vector vào PostgreSQL + pgvector.

```text
HTTP client
  │
  ▼
FastAPI (/api/v1)
  │  request ID middleware + Pydantic schemas
  ▼
Document services
  ├─ parser registry
  ├─ deterministic chunker
  ├─ embedding provider
  └─ local document storage
  │
  ▼
Document repository ── SQLAlchemy async ── PostgreSQL + pgvector
```

## Application layers

### API layer

`app/main.py` tạo FastAPI app, cấu hình logging trong lifespan, thêm `RequestIDMiddleware` và mount router ở `/api/v1`.

Các endpoint hiện có:

- `GET /api/v1/health`
- `POST /api/v1/documents`
- `GET /api/v1/documents/{document_id}`
- `POST /api/v1/documents/search`

`app/api/v1/endpoints/documents.py` kiểm tra file rỗng/kích thước, gọi service qua dependency injection, và chuyển lỗi domain thành HTTP 400, 413, 415, 422, 502 hoặc 500 khi phù hợp.

### Schema layer

`app/schemas/` chứa Pydantic schema. `DocumentResponse` là metadata được API trả về. `DocumentSearchRequest` nhận query, optional document IDs và limit 1–20; `DocumentSearchResponse` trả các chunk phù hợp và metadata nguồn. Schema tách biệt SQLAlchemy models khỏi HTTP contract.

### Service layer

`DocumentIngestionService` điều phối upload processing: chọn parser, tính checksum SHA-256, lưu file, tạo document, parse, chunk, embed, persist chunk và cập nhật status. Lỗi parse/embedding được đánh dấu `failed`; lỗi bất ngờ được wrap thành `DocumentIngestionError` và log.

`DocumentSearchService` embed query rồi yêu cầu repository tìm các chunk gần nhất.

### Repository và data-access layer

`DocumentRepository` chứa persistence/query async. Repository tạo document với `processing` status, persist chunks, đánh dấu `completed`/`failed`, lấy metadata theo owner, và truy vấn cosine similarity. Query search luôn lọc cả `DocumentChunk.owner_id`, `Document.owner_id` và document status `completed`.

## Database models và pgvector

Hai SQLAlchemy model hiện có:

- `Document`: UUID, `owner_id`, filename, MIME type, document type, size, SHA-256 checksum, storage path, processing status, extracted text length, error message và timestamps.
- `DocumentChunk`: UUID, document/owner IDs, thứ tự chunk, text, normalized character offsets, JSONB extraction metadata, vector embedding 256 chiều và timestamp.

`DocumentChunk` có unique constraint `(document_id, chunk_index)`. PostgreSQL có index owner/document và HNSW index `vector_cosine_ops` cho `embedding`. Migration `20260927_0001` bật extension `vector`; `20260927_0002` tạo các bảng/index trên.

## RAG foundation

### Parser abstraction

`DocumentParser` là Protocol có `extract(bytes) -> ExtractedDocument`. `DocumentParserRegistry` chọn parser bằng MIME type hoặc extension:

- PDF: `pypdf.PdfReader`, lưu `page_count`.
- DOCX: `python-docx`, lưu `paragraph_count`.
- TXT và Markdown: UTF-8 text parser.

Parser chỉ trích xuất text/metadata; không biết database, embedding hay HTTP.

### Chunking

`DeterministicTextChunker` chuẩn hóa whitespace, mặc định chunk 1.000 ký tự với overlap 150 ký tự, ưu tiên ngắt ở whitespace. Nó trả `TextChunk` với `index`, `text`, `char_start`, `char_end`. Thuật toán không cần model và có unit test về tính xác định.

### Embedding provider abstraction

`EmbeddingProvider` là Protocol async có `dimensions` và `embed(texts)`. Factory chọn provider từ configuration:

- `deterministic`: hashed token embedding, dùng local development/test; nó kiểm tra pipeline nhưng không phải embedding semantic chất lượng production.
- `openai`: gọi OpenAI embeddings async với model/key được cấu hình.

Schema hiện cố định vector 256 dimensions; factory từ chối dimension khác để tránh mismatch database.

### Storage abstraction

`LocalDocumentStorage` lưu file dưới `<document_storage_dir>/<document UUID>/<safe filename>`. Database chỉ lưu relative `storage_path`; Docker map directory này vào named volume. Đây là adapter local hiện tại, chưa có S3/object-storage adapter.

## Document ingestion flow

```text
Upload multipart file
  → validate non-empty và max size
  → require X-Internal-User-ID
  → chọn parser và tính SHA-256
  → lưu file gốc local
  → tạo metadata document (processing)
  → extract text
  → deterministic chunking
  → generate embeddings
  → lưu chunks + vectors trong PostgreSQL/pgvector
  → document status completed

Search request
  → embed query
  → pgvector cosine distance, filtered by owner/status/(optional document IDs)
  → source-aware chunk results
```

## Ownership boundary hiện tại

Không có authentication. `get_placeholder_owner_id` yêu cầu `X-Internal-User-ID`; giá trị được persist vào document và chunk, sau đó dùng để scope get/search. Đây chỉ là boundary nội bộ tạm thời, không xác thực danh tính và không phải authorization production.

## Configuration và observability

`Settings` đọc `.env` và environment variables có prefix `AI_CAREER_AGENT_`. Cấu hình hiện gồm application/logging, async database URL, local storage path, upload limit và embedding provider/model/dimensions/OpenAI key.

`RequestIDMiddleware` nhận hoặc tạo `X-Request-ID`, đưa lại header trong response, và log method/path/status/duration. Document service log success/failure theo document ID; chưa có distributed tracing, metrics hoặc LLM observability.

## Testing architecture

- Unit tests: config, health check/request ID, parser TXT/Markdown/DOCX, chunker và deterministic embedding provider.
- Integration tests: ingestion persistence và owner/document-scoped retrieval với PostgreSQL/pgvector thật.
- Khi PostgreSQL không chạy, integration fixture skip hai test này; CI cung cấp pgvector PostgreSQL service, chạy migration rồi chạy toàn bộ pytest.

## Chưa tồn tại

Các capability sau chưa được implement và không được xem là behavior hiện tại: authentication, user accounts/workspaces, AI Agent/tool orchestration, CV analysis, JD analysis, skill-gap analysis, personalized learning plan, interview system, Japanese IT communication coaching, LLM answer generation, reranking, hybrid search, background job queue, cloud object storage, production observability và deployment.
