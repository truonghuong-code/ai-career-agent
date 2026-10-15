"""Offline HTTP pipeline; persistence/ownership SQL is tested separately on PostgreSQL."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from app.api.v1.endpoints.analyses import get_analysis_reader, get_analysis_service
from app.db.repositories.analyses import AnalysisChunk, AnalysisInput
from app.integrations.llm.analysis import FakeAnalysisProvider
from app.integrations.llm.provider import LLMProviderError, LLMTimeoutError
from app.main import create_app
from app.schemas.analysis import AnalysisResponse, CVProfile, JDProfile
from app.services.analysis_service import AnalysisService


@pytest.fixture
async def analysis_client():
    doc_id = uuid4()
    source = AnalysisInput(
        doc_id, "a" * 64, "completed", (AnalysisChunk(uuid4(), doc_id, 0, "Python developer"),)
    )
    records = []

    async def save(**values):
        result = AnalysisResponse(
            id=uuid4(),
            document_id=values["document_id"],
            kind=values["kind"],
            version=len(records) + 1,
            status=values["status"],
            document_checksum=values["checksum"],
            created_at=datetime.now(UTC),
            profile=values["profile"],
            sources=values["sources"],
            provenance=values["provenance"],
        )
        records.append(result)
        return result

    repo = SimpleNamespace(
        load_input=AsyncMock(return_value=source),
        save=AsyncMock(side_effect=save),
        get=AsyncMock(),
        list=AsyncMock(),
    )
    service = AnalysisService(repo, FakeAnalysisProvider())
    app = create_app()
    app.dependency_overrides[get_analysis_service] = lambda: service
    app.dependency_overrides[get_analysis_reader] = lambda: AnalysisService(repo)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, service, repo, doc_id, records


@pytest.mark.parametrize(
    "kind,model,field",
    [
        ("cv", CVProfile, "skills"),
        ("jd", JDProfile, "required_skills"),
    ],
)
async def test_p4_t09_create_review_history(analysis_client, kind, model, field):
    client, service, repo, doc_id, records = analysis_client
    data = {name: [] for name in model.model_fields}
    data[field] = [{"value": "Python", "evidence": [{"source_number": 1, "quote": "Python"}]}]
    service.provider = FakeAnalysisProvider(model.model_validate(data))
    headers = {"X-Internal-User-ID": "owner", "X-Request-ID": "analysis-test"}
    path = f"/api/v1/documents/{doc_id}/analyses"
    first = await client.post(path, json={"kind": kind}, headers=headers)
    second = await client.post(path, json={"kind": kind}, headers=headers)
    assert first.status_code == second.status_code == 201
    assert first.headers["X-Request-ID"] == "analysis-test"
    assert first.json()["version"] == 1 and second.json()["version"] == 2
    assert first.json()["profile"] == second.json()["profile"] == data
    assert first.json()["status"] == "completed"
    assert first.json()["sources"][0]["document_id"] == str(doc_id)
    repo.get.return_value = records[0]
    fetched = await client.get(f"/api/v1/analyses/{first.json()['id']}", headers=headers)
    assert fetched.json() == first.json()
    repo.list.return_value = list(reversed(records))
    listing = await client.get(path + f"?kind={kind}&limit=2&offset=0", headers=headers)
    assert [r["version"] for r in listing.json()["analyses"]] == [2, 1]
    assert "profile" not in listing.json()["analyses"][0]
    repo.list.assert_awaited_once_with(doc_id, "owner", kind, 2, 0)
    assert first.json()["provenance"]["prompt_version"] == "analysis-v1"


async def test_p4_t04_insufficient_evidence_persisted(analysis_client):
    client, service, repo, doc_id, records = analysis_client
    response = await client.post(
        f"/api/v1/documents/{doc_id}/analyses",
        json={"kind": "cv"},
        headers={"X-Internal-User-ID": "owner"},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "insufficient_evidence"
    assert all(value == [] for value in response.json()["profile"].values())


@pytest.mark.parametrize("body", [{}, {"kind": "unknown"}, {"kind": 1}, {"kind": "cv", "score": 1}])
async def test_p4_t13_invalid_body(analysis_client, body):
    client, service, repo, doc_id, records = analysis_client
    response = await client.post(
        f"/api/v1/documents/{doc_id}/analyses", json=body, headers={"X-Internal-User-ID": "owner"}
    )
    assert response.status_code == 422
    repo.load_input.assert_not_awaited()


@pytest.mark.parametrize("query", ["?limit=0", "?limit=101", "?offset=-1", "?kind=other"])
async def test_p4_t13_invalid_pagination(analysis_client, query):
    client, service, repo, doc_id, records = analysis_client
    response = await client.get(
        f"/api/v1/documents/{doc_id}/analyses{query}", headers={"X-Internal-User-ID": "owner"}
    )
    assert response.status_code == 422
    repo.list.assert_not_awaited()


@pytest.mark.parametrize("header", [None, " ", "a" * 129])
async def test_p4_t13_invalid_owner(analysis_client, header):
    client, service, repo, doc_id, records = analysis_client
    headers = {} if header is None else {"X-Internal-User-ID": header}
    response = await client.post(
        f"/api/v1/documents/{doc_id}/analyses", json={"kind": "cv"}, headers=headers
    )
    assert response.status_code == 400
    repo.load_input.assert_not_awaited()


@pytest.mark.parametrize(
    "case,status",
    [
        ("missing", 404),
        ("unready", 409),
        ("empty", 422),
        ("oversized", 413),
        ("provider", 502),
        ("timeout", 504),
        ("storage", 503),
    ],
)
async def test_p4_error_pipeline(analysis_client, case, status, caplog):
    from dataclasses import replace

    from sqlalchemy.exc import SQLAlchemyError

    client, service, repo, doc_id, records = analysis_client
    if case == "missing":
        repo.load_input.return_value = None
    elif case == "unready":
        repo.load_input.return_value = replace(repo.load_input.return_value, status="failed")
    elif case == "empty":
        repo.load_input.return_value = replace(repo.load_input.return_value, chunks=())
    elif case == "oversized":
        service.max_context_chars = 1
    elif case == "storage":
        repo.load_input.side_effect = SQLAlchemyError("secret-db")
    else:
        error = LLMTimeoutError if case == "timeout" else LLMProviderError
        service.provider = SimpleNamespace(extract=AsyncMock(side_effect=error("secret-provider")))
    response = await client.post(
        f"/api/v1/documents/{doc_id}/analyses",
        json={"kind": "cv"},
        headers={"X-Internal-User-ID": "owner"},
    )
    assert response.status_code == status
    assert "secret" not in response.text
    assert "secret" not in caplog.text
    assert not records
    repo.save.assert_not_awaited()


async def test_p4_t14_read_routes_do_not_create_provider(analysis_client, monkeypatch):
    from app.api.v1.endpoints import analyses
    from app.core.config import Settings
    from app.db.session import get_db_session

    client, service, repo, doc_id, records = analysis_client
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: None
    monkeypatch.setattr(analyses, "AnalysisRepository", lambda session: repo)
    monkeypatch.setattr(
        analyses, "get_settings", lambda: Settings(_env_file=None, llm_provider="bad")
    )
    repo.list.return_value = []
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as real:
        headers = {"X-Internal-User-ID": "owner"}
        path = f"/api/v1/documents/{doc_id}/analyses"
        response = await real.get(path, headers=headers)
        assert response.status_code == 200
        assert response.json() == {"analyses": []}
        response = await real.post(path, json={"kind": "cv"}, headers=headers)
        assert response.status_code == 503
