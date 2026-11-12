import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_admin_service,
    get_auth_service,
    get_agent_service,
    get_mail_service,
)
from app.agent.service import AgentService
from app.db.schemas import MailMessage, MailSnippet, MailThreadDetails
from app.external_api_clients.llm_client import LLMClient
from app.external_api_clients.schemas import LLMResponse
from app.rag.retrieval.service import RAGRetrievalService
from app.api.agent.schemas import ChatResponse
from app.main import app
from app.db.models.user import User
from app.services.exceptions import ThreadNotFoundError
from app.services.mail_service import MailService


@pytest.fixture
def client():
    auth = MagicMock()
    auth.authenticate = AsyncMock(side_effect=lambda token: (
        User(email="test@example.org", role=token) if token in {"admin", "manager"} else None
    ))
    app.dependency_overrides[get_auth_service] = lambda: auth
    try:
        yield TestClient(app, headers={"Authorization": "Bearer manager"})
    finally:
        app.dependency_overrides.clear()


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_rbac_forbidden_without_required_role(client):
    # Admin-only endpoint with default manager role
    response = client.get("/api/v1/admin/security/events", headers={"Authorization": "Bearer manager"})
    assert response.status_code == 403


def test_search_emails_endpoint(client):
    mock_mail_service = MagicMock()
    mock_mail_service.search_emails = AsyncMock(
        return_value=[
            MailSnippet(
                email_id="e1",
                thread_id="t1",
                subject="Поставка",
                sender="supplier@test.com",
                date=datetime.now(timezone.utc),
                snippet="Сроки отгрузки...",
            )
        ]
    )

    app.dependency_overrides[get_mail_service] = lambda: mock_mail_service
    try:
        response = client.get(
            "/api/v1/emails/search?words=поставка",
            headers={"Authorization": "Bearer manager"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["subject"] == "Поставка"
    finally:
        app.dependency_overrides.clear()


def test_search_api_accepts_sender_without_words_and_rejects_empty_query(client):
    service = MagicMock()
    service.search_emails = AsyncMock(return_value=[])
    app.dependency_overrides[get_mail_service] = lambda: service
    try:
        endpoint = "/api/v1/emails/search"
        assert client.get(endpoint, params={"sender": "director@progress-corp.ru"}).status_code == 200
        service.search_emails.assert_awaited_once_with(
            words=None, sender="director@progress-corp.ru", participant=None,
            start_date=None, end_date=None,
        )
        assert client.get(endpoint, params={"words": " "}).status_code == 422
        assert service.search_emails.await_count == 1
    finally:
        app.dependency_overrides.clear()


def test_get_thread_not_found(client):
    mock_mail_service = MagicMock()
    mock_mail_service.get_thread = AsyncMock(
        side_effect=ThreadNotFoundError("Thread not found")
    )

    app.dependency_overrides[get_mail_service] = lambda: mock_mail_service
    try:
        test_uuid = str(uuid.uuid4())
        response = client.get(
            f"/api/v1/emails/threads/{test_uuid}",
            headers={"Authorization": "Bearer manager"},
        )
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_close_thread_endpoint(client):
    test_uuid = uuid.uuid4()
    mock_mail_service = MagicMock()
    mock_mail_service.close_thread = AsyncMock(
        return_value={
            "status": "closed",
            "thread_id": str(test_uuid),
            "queued_for_rag": True,
        }
    )

    app.dependency_overrides[get_mail_service] = lambda: mock_mail_service
    try:
        response = client.post(
            f"/api/v1/emails/threads/{test_uuid}/close",
            headers={"Authorization": "Bearer manager"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "closed"
        assert data["queued_for_rag"] is True
    finally:
        app.dependency_overrides.clear()


def test_agent_chat_endpoint(client):
    mock_agent_service = MagicMock()
    mock_agent_service.chat = AsyncMock(
        return_value=ChatResponse(
            run_id="run_12345",
            response="Ответ агента",
            is_blocked=False,
        )
    )

    app.dependency_overrides[get_agent_service] = lambda: mock_agent_service
    try:
        response = client.post(
            "/api/v1/agent/chat",
            json={"message": "Здравствуйте"},
            headers={"Authorization": "Bearer manager"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == "run_12345"
        assert data["response"] == "Ответ агента"
        assert data["is_blocked"] is False
    finally:
        app.dependency_overrides.clear()


def test_agent_searches_mail_through_http(client):
    llm = MagicMock(spec=LLMClient)
    mail = MagicMock(spec=MailService)
    llm.chat = AsyncMock(side_effect=[
        LLMResponse(content='{"task":"search"}'),
        LLMResponse(tool_calls=[{"name": "search_emails", "args": {
            "words": "98123", "sender": "ivan", "start_date": "2026-11-01",
        }}]),
    ])
    mail.search_emails = AsyncMock(return_value=[MailSnippet(
        "email-id", "thread-id", "Проект X", "ivan@example.org",
        datetime(2026, 11, 1, tzinfo=timezone.utc), "Поставка оборудования",
    )])
    agent = AgentService(llm, mail, MagicMock(spec=RAGRetrievalService))
    app.dependency_overrides[get_agent_service] = lambda: agent

    response = client.post("/api/v1/agent/chat", json={
        "message": "Найди письма от Ивана по артикулу 98123 с 1 ноября 2026 года",
    })

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert "email-id" in response.json()["response"]
    criteria = mail.search_emails.await_args.kwargs
    assert criteria["words"] == "98123" and criteria["sender"] == "ivan"
    assert criteria["start_date"].isoformat() == "2026-11-01"


def test_admin_ingest_document_endpoint(client):
    mock_admin_service = MagicMock()
    mock_admin_service.ingest_document = AsyncMock(
        return_value={
            "status": "queued",
            "doc_id": "doc_1",
            "title": "Регламент",
            "queue": "rag.documents.queue",
        }
    )

    app.dependency_overrides[get_admin_service] = lambda: mock_admin_service
    try:
        response = client.post(
            "/api/v1/admin/documents",
            json={
                "doc_id": "doc_1",
                "title": "Регламент",
                "file_path": "data/doc.md",
            },
            headers={"Authorization": "Bearer admin"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"
    finally:
        app.dependency_overrides.clear()


def test_mail_dependency_builds_real_service():
    from app.api.dependencies import get_mail_service

    repo, producer = MagicMock(), MagicMock()
    service = get_mail_service(mail_repo=repo, rag_producer=producer)
    assert service._mail_repo is repo
    assert service._rag_producer is producer


def test_token_endpoint_and_server_role(client):
    scheme = app.openapi()["components"]["securitySchemes"]["OAuth2PasswordBearer"]
    assert scheme["flows"]["password"]["tokenUrl"] == "/api/v1/auth/token"

    auth = MagicMock()
    auth.login = AsyncMock(side_effect=[None, "issued-token"])
    auth.authenticate = AsyncMock(return_value=User(email="test@example.org", role="manager"))
    app.dependency_overrides[get_auth_service] = lambda: auth
    payload = {"username": "test@example.org", "password": "test-password"}

    assert client.post("/api/v1/auth/token", data=payload).status_code == 401
    response = client.post("/api/v1/auth/token", data=payload)
    assert response.json() == {"access_token": "issued-token", "token_type": "bearer"}
    auth.login.assert_awaited_with("test@example.org", "test-password")
    assert client.get(
        "/api/v1/admin/security/events",
        headers={"Authorization": "Bearer issued-token", "X-User-Role": "admin"},
    ).status_code == 403
    assert TestClient(app).get("/api/v1/admin/security/events").status_code == 401
