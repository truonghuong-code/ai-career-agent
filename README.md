# AI Career Agent

Backend foundation for an AI-powered career-development application focused on AI Engineer and BrSE career paths.

Phases 1–4 provide document lifecycle, retrieval, grounded Q&A and CV/JD extraction: PDF, DOCX, TXT, and Markdown extraction; deterministic chunking; pluggable embeddings; pgvector cosine retrieval; and source-aware search results. It intentionally contains no AI agent, skill-gap scoring, authentication, or interview functionality.

## Prerequisites

- Python 3.11 or newer
- Docker and Docker Compose (for PostgreSQL)

## Local setup

1. Create a virtual environment and install the project with development dependencies:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -e ".[dev]"
   ```

2. Create your local environment file. Do not commit it:

   ```bash
   cp .env.example .env
   ```

   Application settings use the `AI_CAREER_AGENT_` prefix to avoid conflicts with
   variables from the host environment.

3. Start PostgreSQL with pgvector:

   ```bash
   docker compose up -d db
   ```

4. Apply database migrations:

   ```bash
   alembic upgrade head
   ```

5. Run the API:

   ```bash
   uvicorn app.main:app --reload
   ```

Open `http://localhost:8000/docs` for the OpenAPI documentation. The health endpoint is available at `GET /api/v1/health`.

## Document ingestion and retrieval

Document endpoints temporarily use the required `X-Internal-User-ID` header as an ownership boundary. This is a deliberate placeholder that will be replaced by authentication in Phase 6.

Upload a supported file (`.pdf`, `.docx`, `.txt`, `.md`) and process it synchronously:

```bash
curl -X POST http://localhost:8000/api/v1/documents \
  -H "X-Internal-User-ID: local-user" \
  -F "file=@example.txt"
```

Retrieve document metadata:

```bash
curl http://localhost:8000/api/v1/documents/<document-id> \
  -H "X-Internal-User-ID: local-user"
```

Search only documents owned by that internal user. Results include chunk text, score, filename, document ID, offsets, and extraction metadata:

```bash
curl -X POST http://localhost:8000/api/v1/documents/search \
  -H "Content-Type: application/json" \
  -H "X-Internal-User-ID: local-user" \
  -d '{"query":"FastAPI PostgreSQL", "limit": 5}'
```

`AI_CAREER_AGENT_EMBEDDING_PROVIDER=deterministic` is the default for local development and tests. It creates stable hashed token vectors so the complete ingestion pipeline runs without a key. For production-quality semantic retrieval, set `AI_CAREER_AGENT_EMBEDDING_PROVIDER=openai` and provide `AI_CAREER_AGENT_OPENAI_API_KEY`; the configured OpenAI model must support the configured 256 dimensions. Original uploads are stored in the configured local `uploads/` directory (or its Docker volume).

## Docker

To run the API and database as containers:

```bash
docker compose up --build
```

In a second terminal, run migrations:

```bash
docker compose run --rm api alembic upgrade head
```

The API is exposed on `http://localhost:8000`; PostgreSQL is exposed on `localhost:5432`.

## Development commands

```bash
pytest
ruff check .
ruff format --check .
```

The integration tests require a running local PostgreSQL/pgvector container and migrations applied:

```bash
docker compose up -d db
alembic upgrade head
pytest
```

## Project layout

```text
app/api/          HTTP routes
app/core/         Configuration and logging
app/db/           SQLAlchemy setup, models, and Alembic migrations
app/schemas/      Shared Pydantic schemas
app/services/     Document and grounded Q&A services
app/agents/       Agent orchestration (reserved for later phases)
app/tools/        Agent tools (reserved for later phases)
app/rag/          Parsing, chunking, embeddings, and retrieval components
app/integrations/ External provider and storage adapters
tests/            Unit and integration tests
```


## Grounded Q&A

```bash
curl -X POST http://localhost:8000/api/v1/qa \
  -H "Content-Type: application/json" \
  -H "X-Internal-User-ID: local-user" \
  -d '{"question":"What Python experience is documented?", "limit":5}'
```

Response fields are `answer`, `status` and `sources`. Each source contains
`number`, `document_id`, `chunk_id`, `chunk_index`; source numbers match
`[Source N]` citations and retain retrieval order. Optional `document_ids` filters
owned completed documents (`[]` selects none). Empty retrieval returns `no_context`
without an LLM call; unsupported evidence returns `insufficient_evidence`.
Both have no citations. Provider errors return 502, timeout 504, retrieval
infrastructure/configuration errors 503. Invalid input returns 422; missing owner 400.

`AI_CAREER_AGENT_LLM_PROVIDER=fake` is the offline default. It conservatively
returns insufficient evidence, not a semantic answer. Tests inject deterministic
responses to verify successful answers. For live generation configure
`AI_CAREER_AGENT_LLM_PROVIDER=openai` and `AI_CAREER_AGENT_OPENAI_API_KEY`.
The configured model must support Chat Completions structured JSON output.
Default model: `gpt-4o-mini`; timeout: 30 seconds; output limit: 1024 tokens;
context limit: 5 chunks. See `.env.example` for all settings. Live OpenAI use
incurs API costs; automated tests never call it.

Citation validation ensures source identity, not factual correctness of model
claims. Prompt instructions treat document content as untrusted data, but do not
guarantee injection resistance. Production authentication remains out of scope.

Integration fixtures truncate document tables. Run integration tests only against
an isolated test database, never a development database with documents to preserve.


## CV and Job Description analysis (Phase 4)

After ingesting a document, request an extraction explicitly as `cv` or `jd`:

```bash
curl -X POST http://localhost:8000/api/v1/documents/<document-id>/analyses \
  -H "Content-Type: application/json" \
  -H "X-Internal-User-ID: local-user" \
  -d '{"kind":"cv"}'

curl 'http://localhost:8000/api/v1/documents/<document-id>/analyses?kind=cv&limit=20&offset=0' \
  -H "X-Internal-User-ID: local-user"

curl http://localhost:8000/api/v1/analyses/<analysis-id> \
  -H "X-Internal-User-ID: local-user"
```

Creation returns 201 with an immutable version, typed profile, source snapshots and
provenance. Each nonempty fact has `value` and `evidence` containing source numbers
and verbatim quotes. CV fields: headline, skills, experience, education,
certifications, languages. JD fields: title, employer, required_skills,
preferred_skills, responsibilities, qualifications, languages. Missing facts are
empty arrays. Every POST creates a new version per document/kind. List returns
metadata only; get returns the stored profile and evidence. Deleting a document
also deletes its analyses. File format `document_type` remains unchanged.

Apply `alembic upgrade head` before using Phase 4. It adds the analysis table without
changing document data. Uses the existing LLM provider/model/key/timeout settings;
new settings are `AI_CAREER_AGENT_ANALYSIS_MAX_CONTEXT_CHARS=40000` and
`AI_CAREER_AGENT_ANALYSIS_MAX_OUTPUT_TOKENS=4096`. Context over budget is rejected
with 413, never silently truncated. Empty text yields 422, incomplete/changed
documents 409, unavailable resources 404, provider failures 502, timeout 504,
storage/configuration failures 503. Fake provider conservatively returns empty
profiles (`insufficient_evidence`); live extraction requires selecting OpenAI.

Evidence checks establish traceability, not factual accuracy; review extracted
profiles before use. No matching scores, skill-gap calculation or learning plans.
Full contracts: [Phase 4 specification](docs/specs/phase-4.md).
