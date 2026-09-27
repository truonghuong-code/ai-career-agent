# AI Career Agent

Backend foundation for an AI-powered career-development application focused on AI Engineer and BrSE career paths.

Phase 1 adds document ingestion and a RAG foundation: PDF, DOCX, TXT, and Markdown extraction; deterministic chunking; pluggable embeddings; pgvector cosine retrieval; and source-aware search results. It intentionally contains no AI agent, CV/JD analysis, authentication, or interview functionality.

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
app/services/     Application services (reserved for later phases)
app/agents/       Agent orchestration (reserved for later phases)
app/tools/        Agent tools (reserved for later phases)
app/rag/          Parsing, chunking, embeddings, and retrieval components
app/integrations/ External provider and storage adapters
tests/            Unit and integration tests
```
