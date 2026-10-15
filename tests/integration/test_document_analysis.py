"""Real PostgreSQL/pgvector persistence, ownership, concurrency and deletion tests."""

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.v1.endpoints.analyses import get_analysis_reader, get_analysis_service
from app.db.models.analysis import DocumentAnalysis
from app.db.models.document import Document, DocumentChunk
from app.db.repositories.analyses import AnalysisRepository
from app.db.repositories.documents import DocumentRepository
from app.integrations.llm.analysis import FakeAnalysisProvider
from app.integrations.storage.local import LocalDocumentStorage
from app.main import create_app
from app.rag.chunking import DeterministicTextChunker
from app.rag.embeddings import DeterministicEmbeddingProvider
from app.rag.parsers import DocumentParserRegistry
from app.schemas.analysis import CVProfile, JDProfile
from app.services.analysis_service import (
    AnalysisNotFoundError,
    AnalysisNotReadyError,
    AnalysisService,
)
from app.services.document_service import DocumentIngestionService


@pytest.fixture
async def analysis_document(db_session, storage_dir):
    ingestion = DocumentIngestionService(
        DocumentRepository(db_session),
        DocumentParserRegistry(),
        DeterministicTextChunker(),
        DeterministicEmbeddingProvider(256),
        LocalDocumentStorage(storage_dir),
    )
    result = await ingestion.ingest(
        owner_id="owner",
        filename="profile.txt",
        mime_type="text/plain",
        content=b"Python developer with FastAPI experience.",
    )
    return result.document.id


def provider(kind="cv"):
    model = CVProfile if kind == "cv" else JDProfile
    data = {name: [] for name in model.model_fields}
    data["skills" if kind == "cv" else "required_skills"] = [
        {"value": "Python", "evidence": [{"source_number": 1, "quote": "Python"}]},
    ]
    return FakeAnalysisProvider(model.model_validate(data))


@pytest.mark.parametrize("kind", ["cv", "jd"])
async def test_p4_t09_real_api_persistence(db_session, analysis_document, kind):
    service = AnalysisService(AnalysisRepository(db_session), provider(kind))
    app = create_app()
    app.dependency_overrides[get_analysis_service] = lambda: service
    app.dependency_overrides[get_analysis_reader] = lambda: service
    headers = {"X-Internal-User-ID": "owner"}
    path = f"/api/v1/documents/{analysis_document}/analyses"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = await client.post(path, json={"kind": kind}, headers=headers)
        second = await client.post(path, json={"kind": kind}, headers=headers)
        assert first.status_code == second.status_code == 201
        assert [first.json()["version"], second.json()["version"]] == [1, 2]
        fetched = await client.get(f"/api/v1/analyses/{first.json()['id']}", headers=headers)
        assert fetched.json() == first.json()
        listed = await client.get(path + "?limit=1", headers=headers)
        assert listed.json()["analyses"][0]["version"] == 2
        assert "profile" not in listed.json()["analyses"][0]
        field = "skills" if kind == "cv" else "required_skills"
        assert first.json()["profile"][field][0]["evidence"][0]["quote"] == "Python"
        assert first.json()["sources"][0]["text"] == "Python developer with FastAPI experience."
        assert (await client.get(path, headers={"X-Internal-User-ID": "other"})).status_code == 404
        assert (
            await client.get(
                f"/api/v1/analyses/{first.json()['id']}", headers={"X-Internal-User-ID": "other"}
            )
        ).status_code == 404
        assert (
            await client.post(path, json={"kind": kind}, headers={"X-Internal-User-ID": "other"})
        ).status_code == 404


async def test_p4_t10_concurrent_versions_and_independent_kinds(db_session, analysis_document):
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def create(kind):
        async with sessions() as session:
            return await AnalysisService(AnalysisRepository(session), provider(kind)).create(
                analysis_document,
                "owner",
                kind,
            )

    results = await asyncio.gather(create("cv"), create("cv"), create("jd"))
    assert sorted(r.version for r in results if r.kind == "cv") == [1, 2]
    assert [r.version for r in results if r.kind == "jd"] == [1]
    assert len({r.id for r in results}) == 3


async def test_p4_t11_chunk_and_analysis_owner_filters(db_session, analysis_document):
    repository = AnalysisRepository(db_session)
    result = await AnalysisService(repository, provider()).create(analysis_document, "owner", "cv")
    await db_session.execute(
        update(DocumentAnalysis).where(DocumentAnalysis.id == result.id).values(owner_id="other")
    )
    await db_session.commit()
    assert await repository.get(result.id, "owner") is None
    assert await repository.get(result.id, "other") is None
    await db_session.execute(
        update(DocumentChunk)
        .where(DocumentChunk.document_id == analysis_document)
        .values(owner_id="other")
    )
    await db_session.commit()
    assert (await repository.load_input(analysis_document, "owner")).chunks == ()
    assert await repository.load_input(analysis_document, "other") is None


async def test_p4_t12_source_delete_cascades(db_session, analysis_document):
    service = AnalysisService(AnalysisRepository(db_session), provider())
    result = await service.create(analysis_document, "owner", "cv")
    await DocumentRepository(db_session).delete_document(analysis_document, "owner")
    assert await db_session.scalar(select(func.count()).select_from(DocumentAnalysis)) == 0
    with pytest.raises(AnalysisNotFoundError):
        await service.get(result.id, "owner")


async def test_p4_t15_source_deleted_during_generation(db_session, analysis_document):
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)
    fake = provider()
    original = fake.extract

    async def delete_then_extract(messages, kind):
        async with sessions() as session:
            await DocumentRepository(session).delete_document(analysis_document, "owner")
        return await original(messages, kind)

    fake.extract = delete_then_extract
    with pytest.raises(AnalysisNotReadyError):
        await AnalysisService(AnalysisRepository(db_session), fake).create(
            analysis_document,
            "owner",
            "cv",
        )
    assert await db_session.scalar(select(func.count()).select_from(DocumentAnalysis)) == 0


async def test_p4_t05_failed_document_never_generates(db_session, analysis_document):
    await db_session.execute(
        update(Document).where(Document.id == analysis_document).values(processing_status="failed")
    )
    await db_session.commit()
    fake = provider()
    fake.extract = AsyncMock()
    with pytest.raises(AnalysisNotReadyError):
        await AnalysisService(AnalysisRepository(db_session), fake).create(
            analysis_document,
            "owner",
            "cv",
        )
    fake.extract.assert_not_awaited()


async def test_p4_t16_database_constraints_and_failed_save_rollback(db_session, analysis_document):
    from sqlalchemy.exc import IntegrityError

    service = AnalysisService(AnalysisRepository(db_session), provider())
    first = await service.create(analysis_document, "owner", "cv")
    for changes in ({"version": 0}, {"kind": "xx"}, {"version": 1}):
        values = (
            dict(
                document_id=analysis_document,
                owner_id="owner",
                kind="cv",
                version=2,
                status="completed",
                document_checksum=first.document_checksum,
                profile=first.profile.model_dump(mode="json"),
                sources=[s.model_dump(mode="json") for s in first.sources],
                provenance=first.provenance.model_dump(mode="json"),
            )
            | changes
        )
        db_session.add(DocumentAnalysis(**values))
        with pytest.raises(IntegrityError):
            await db_session.flush()
        await db_session.rollback()
    second = await service.create(analysis_document, "owner", "cv")
    assert second.version == 2
    assert (await service.get(first.id, "owner")).profile == first.profile
