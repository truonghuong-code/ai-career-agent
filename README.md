# AI Career Agent

Backend foundation for an AI-powered career-development application focused on AI Engineer and BrSE career paths.

The current phase provides only application infrastructure: FastAPI, configuration, structured request logging, PostgreSQL with pgvector, Alembic, tests, linting, Docker, and CI. It intentionally contains no business features, AI agent, RAG pipeline, or authentication.

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

## Project layout

```text
app/api/          HTTP routes
app/core/         Configuration and logging
app/db/           SQLAlchemy setup, models, and Alembic migrations
app/schemas/      Shared Pydantic schemas
app/services/     Application services (reserved for later phases)
app/agents/       Agent orchestration (reserved for later phases)
app/tools/        Agent tools (reserved for later phases)
app/rag/          RAG components (reserved for later phases)
app/integrations/ External provider adapters (reserved for later phases)
tests/            Unit and integration tests
```
