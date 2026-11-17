from hashlib import sha256
from urllib.parse import parse_qs, urlsplit
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
from cryptography.fernet import Fernet

from app.db.dao.gmail.gmail import GmailDAO
from app.db.enums import GmailConnectionStatus
from app.db.models import GmailAccount, GmailConnection
from app.external_api_clients.gmail.client import GMAIL_READONLY, GmailClient
from app.services.gmail.gmail_service import GmailService

CALLBACK_URI = "https://api.example.test/api/v1/gmail/oauth/callback"


def make_dao(cipher: Fernet) -> tuple[MagicMock, GmailAccount, GmailConnection]:
    account = GmailAccount(id=uuid4(), owner_id=uuid4(), name="Work")
    connection = GmailConnection(
        gmail_account_id=account.id,
        pending_client_id="client-id",
        pending_client_secret_ciphertext=cipher.encrypt(b"client-secret").decode(),
        status=GmailConnectionStatus.PENDING,
        generation=0,
    )
    dao = MagicMock(spec=GmailDAO)
    transaction = MagicMock()
    transaction.__aenter__ = AsyncMock()
    transaction.__aexit__ = AsyncMock(return_value=False)
    dao.transaction.return_value = transaction
    dao.lock_account.return_value = account
    dao.lock_connection.return_value = connection
    dao.lock_oauth_attempt.return_value = connection
    return dao, account, connection


async def test_gmail_oauth_verifies_scope_and_encrypts_refresh_token() -> None:
    cipher = Fernet(Fernet.generate_key())
    dao, account, connection = make_dao(cipher)

    def google(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            fields = parse_qs(request.content.decode())
            assert fields["redirect_uri"] == [CALLBACK_URI]
            assert fields["client_secret"] == ["client-secret"]
            assert fields["code_verifier"] == [attempt.browser_token]
            return httpx.Response(200, json={
                "access_token": "access", "refresh_token": "refresh",
                "scope": GMAIL_READONLY,
            })
        assert request.url.path == "/gmail/v1/users/me/profile"
        assert request.headers["Authorization"] == "Bearer access"
        return httpx.Response(200, json={"emailAddress": "Manager@example.test"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(google)) as http:
        service = GmailService(dao, GmailClient(http, CALLBACK_URI), cipher)
        attempt = await service.start(account.owner_id, account.id)
        query = parse_qs(urlsplit(attempt.url).query)
        assert query["access_type"] == ["offline"]
        assert query["code_challenge_method"] == ["S256"]
        assert "client-secret" not in attempt.url
        assert await service.complete(query["state"][0], attempt.browser_token, "code")

    args = dao.lock_oauth_attempt.await_args.args
    assert args[1] == sha256(query["state"][0].encode()).hexdigest()
    assert args[2] == sha256(attempt.browser_token.encode()).hexdigest()
    assert account.gmail_email == "manager@example.test"
    assert connection.scopes == [GMAIL_READONLY]
    assert cipher.decrypt(connection.refresh_token_ciphertext) == b"refresh"
    assert connection.status == GmailConnectionStatus.CONNECTED
    assert connection.oauth_state_digest is None


async def test_gmail_oauth_rejects_unclaimed_callback() -> None:
    cipher = Fernet(Fernet.generate_key())
    dao, _, _ = make_dao(cipher)
    dao.lock_oauth_attempt.return_value = None
    client = AsyncMock(spec=GmailClient)
    service = GmailService(dao, client, cipher)

    assert not await service.complete("expired", "another-browser", "code")
    client.exchange_code.assert_not_awaited()


def test_gmail_connection_validation_does_not_echo_secrets() -> None:
    from fastapi.testclient import TestClient

    from app.api.dependencies import get_auth_service
    from app.api.gmail.router import get_gmail_service
    from app.db.models import User
    from app.main import app

    service = AsyncMock(spec=GmailService)
    auth = AsyncMock()
    auth.authenticate.return_value = User(id=uuid4(), role="manager")
    app.dependency_overrides[get_auth_service] = lambda: auth
    app.dependency_overrides[get_gmail_service] = lambda: service
    try:
        client = TestClient(app)
        url = f"/api/v1/gmail/accounts/{uuid4()}/connection"
        response = client.put(
            url,
            json={"client_id": "client", "client_secret": {"value": "sensitive"}},
            headers={"Authorization": "Bearer manager"},
        )
        assert response.status_code == 422
        assert "sensitive" not in response.text
        service.configure.assert_not_awaited()
    finally:
        app.dependency_overrides.pop(get_auth_service)
        app.dependency_overrides.pop(get_gmail_service)
