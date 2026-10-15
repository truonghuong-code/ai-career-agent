from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints.qa import get_qa_service
from app.core.config import Settings
from app.integrations.llm.provider import LLMProviderError, LLMTimeoutError
from app.main import create_app
from app.services.qa_service import GroundedAnswer, QAEmbeddingError, QARetrievalError


@pytest.fixture
def qa_client():
    app = create_app()
    service = SimpleNamespace(
        answer=AsyncMock(return_value=GroundedAnswer("No evidence", "no_context", ()))
    )
    app.dependency_overrides[get_qa_service] = lambda: service
    with TestClient(app) as client:
        yield client, service


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"question": ""},
        {"question": " \n "},
        {"question": 123},
        {"question": "x" * 5001},
        {"question": "x", "limit": 21},
        {"question": "x", "document_ids": ["not-uuid"]},
        {"question": "x", "limit": True},
    ],
)
def test_invalid_body(qa_client, body):
    client, service = qa_client
    assert (
        client.post("/api/v1/qa", json=body, headers={"X-Internal-User-ID": "owner"}).status_code
        == 422
    )
    service.answer.assert_not_awaited()


def test_header_and_response_contract(qa_client):
    client, service = qa_client
    assert client.post("/api/v1/qa", json={"question": "Python?"}).status_code == 400
    service.answer.assert_not_awaited()
    response = client.post(
        "/api/v1/qa",
        json={"question": " Python? ", "document_ids": []},
        headers={"X-Internal-User-ID": " owner ", "X-Request-ID": "qa-test"},
    )
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "qa-test"
    assert response.json() == {"answer": "No evidence", "status": "no_context", "sources": []}
    service.answer.assert_awaited_once_with(
        owner_id="owner", question="Python?", limit=5, document_ids=[]
    )


@pytest.mark.parametrize(
    "error,status",
    [
        (LLMProviderError, 502),
        (LLMTimeoutError, 504),
        (QAEmbeddingError, 502),
        (QARetrievalError, 503),
    ],
)
def test_safe_http_errors(qa_client, error, status):
    client, service = qa_client
    service.answer.side_effect = error("secret key and internal stack")
    response = client.post(
        "/api/v1/qa", json={"question": "Python?"}, headers={"X-Internal-User-ID": "owner"}
    )
    assert response.status_code == status
    assert "secret" not in response.text
    assert "X-Request-ID" in response.headers


def test_invalid_configuration_is_safe(monkeypatch):
    from app.api.v1.endpoints import qa
    from app.db.session import get_db_session

    monkeypatch.setattr(
        qa, "get_settings", lambda: Settings(_env_file=None, llm_provider="invalid")
    )
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: None
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/qa", json={"question": "Python?"}, headers={"X-Internal-User-ID": "owner"}
        )
    assert response.status_code == 503
    assert response.json() == {"detail": "Question answering is not configured"}
