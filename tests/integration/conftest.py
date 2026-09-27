import os
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings


@pytest.fixture(scope="session")
def database_url() -> str:
    return os.environ.get("AI_CAREER_AGENT_DATABASE_URL", get_settings().database_url)


@pytest.fixture
async def db_session(database_url: str) -> AsyncSession:
    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("TRUNCATE TABLE document_chunks, documents CASCADE"))
    except OSError:
        await engine.dispose()
        pytest.skip(
            "PostgreSQL/pgvector is not available; start Docker Compose to run integration tests"
        )
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def storage_dir(tmp_path: Path) -> Path:
    return tmp_path / "uploads"
