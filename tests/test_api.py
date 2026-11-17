import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_admin_service,
    get_auth_service,
    get_agent_service,
    get_email_retrieval_service,
    get_raw_email_service,
    get_thread_service,
)
from app.agent.service import AgentService
from app.db.dao.db_mail.raw_email import RawEmailDAO
from app.dto.db_mail import MailMessage, MailSearchCriteria, MailSnippet
from app.external_api_clients.llm_client import LLMClient
from app.external_api_clients.schemas import LLMResponse
from app.services.rag.retrieval.document.service import DocumentRetrievalService
from app.api.agent.schemas import ChatResponse
from app.main import app
from app.db.models.user import User
from app.services.exceptions import ThreadNotFoundError
from app.services.db_mail.thread import ThreadService
from app.services.db_mail.draft import DraftService
from app.services.db_mail.raw_email import RawEmailService
from app.services.rag.retrieval.email.service import EmailRetrievalService


@pytest.fixture
def client():
    auth = MagicMock()
    auth.authenticate = AsyncMock(side_effect=lambda token: (
        User(id=uuid.UUID(int=1), email="test@example.org", role=token) if token in {"admin", "manager"} else None
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


def test_get_email_passes_owner_and_returns_404_for_unavailable_message(
    client: TestClient,
) -> None:
    email_id, thread_id = uuid.uuid4(), uuid.uuid4()
    message = MailMessage(
        id=str(email_id), thread_id=str(thread_id), sender="sender@example.test",
        recipient="manager@example.test", date=datetime.now(timezone.utc),
        subject="Поставка", body="Полный текст письма.",
    )
    dao = AsyncMock(spec=RawEmailDAO)
    dao.get_email.side_effect = [message, None]
    app.dependency_overrides[get_raw_email_service] = lambda: RawEmailService(dao)
    endpoint = f"/api/v1/emails/{email_id}"

    response = client.get(endpoint)
    assert response.status_code == 200
    assert response.json()["body"] == message.body
    assert client.get(endpoint).status_code == 404
    assert TestClient(app).get(endpoint).status_code == 401
    assert dao.get_email.await_count == 2
    for call in dao.get_email.await_args_list:
        assert call.args == (email_id,)
        assert call.kwargs == {"owner_id": uuid.UUID(int=1)}


def test_search_emails_endpoint(client):
    service = MagicMock()
    service.search = AsyncMock(
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

    app.dependency_overrides[get_email_retrieval_service] = lambda: service
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
    service.search = AsyncMock(return_value=[])
    app.dependency_overrides[get_email_retrieval_service] = lambda: service
    try:
        endpoint = "/api/v1/emails/search"
        assert client.get(endpoint, params={"sender": "director@progress-corp.ru"}).status_code == 200
        service.search.assert_awaited_once_with(
            MailSearchCriteria(sender="director@progress-corp.ru"),
            owner_id=uuid.UUID(int=1),
        )
        assert client.get(endpoint, params={"words": " "}).status_code == 422
        assert service.search.await_count == 1
    finally:
        app.dependency_overrides.clear()


def test_get_thread_not_found(client):
    service = MagicMock()
    service.get_thread = AsyncMock(
        side_effect=ThreadNotFoundError("Thread not found")
    )

    app.dependency_overrides[get_thread_service] = lambda: service
    try:
        test_uuid = str(uuid.uuid4())
        response = client.get(
            f"/api/v1/emails/threads/{test_uuid}",
            headers={"Authorization": "Bearer manager"},
        )
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_thread_close_route_is_removed(client: TestClient) -> None:
    assert client.post(f"/api/v1/emails/threads/{uuid.uuid4()}/close").status_code == 404


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
    email_search = MagicMock(spec=EmailRetrievalService)
    llm.chat = AsyncMock(side_effect=[
        LLMResponse(content='{"task":"search"}'),
        LLMResponse(tool_calls=[{"name": "search_emails", "args": {
            "words": "98123", "sender": "ivan", "start_date": "2026-11-01",
        }}]),
    ])
    email_search.search = AsyncMock(return_value=[MailSnippet(
        "email-id", "thread-id", "Проект X", "ivan@example.org",
        datetime(2026, 11, 1, tzinfo=timezone.utc), "Поставка оборудования",
    )])
    agent = AgentService(
        llm, email_search, MagicMock(spec=ThreadService), MagicMock(spec=DraftService),
        MagicMock(spec=DocumentRetrievalService),
    )
    app.dependency_overrides[get_agent_service] = lambda: agent

    response = client.post("/api/v1/agent/chat", json={
        "message": "Найди письма от Ивана по артикулу 98123 с 1 ноября 2026 года",
    })

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert "email-id" in response.json()["response"]
    criteria = email_search.search.await_args.args[0]
    assert email_search.search.await_args.kwargs["owner_id"] == uuid.UUID(int=1)
    assert criteria.words == "98123" and criteria.sender == "ivan"
    assert criteria.start_date.isoformat() == "2026-11-01"


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
