from base64 import urlsafe_b64encode
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import parse_qs
from uuid import uuid4

import httpx
from cryptography.fernet import Fernet

from app.db.enums import GmailConnectionStatus
from app.db.dao.gmail.gmail import GmailDAO
from app.db.models import GmailConnection
from app.dto.gmail import GmailSyncLease
from app.external_api_clients.gmail.client import GmailClient
from app.services.gmail.gmail_sync_service import GmailSyncService


def make_lease(cipher: Fernet, cursor: datetime | None = None) -> GmailSyncLease:
    return GmailSyncLease(
        uuid4(), "mailbox@example.test", "client",
        cipher.encrypt(b"client-secret").decode(),
        cipher.encrypt(b"refresh-token").decode(),
        cursor, uuid4(), 1,
    )


def make_dao(lease: GmailSyncLease) -> tuple[MagicMock, GmailConnection]:
    dao = MagicMock(spec=GmailDAO)
    session = MagicMock()
    transaction = MagicMock()
    transaction.__aenter__ = AsyncMock(return_value=session)
    transaction.__aexit__ = AsyncMock(return_value=False)
    dao.transaction.return_value = transaction
    connection = GmailConnection(
        gmail_account_id=lease.account_id,
        status=GmailConnectionStatus.SYNCING,
        synced_through_at=lease.synced_through_at,
    )
    dao.lock_sync_connection.return_value = connection
    dao.existing_message_ids.return_value = set()
    dao.upsert_thread.return_value = uuid4()
    return dao, connection


def message(
    message_id: str, date: datetime, content: str, *,
    mime: str = "text/plain", labels: tuple[str, ...] = (),
) -> dict[str, object]:
    return {
        "id": message_id,
        "threadId": "thread-1",
        "internalDate": str(int(date.timestamp() * 1000)),
        "labelIds": list(labels),
        "payload": {
            "mimeType": mime,
            "headers": [
                {"name": "From", "value": "Client <client@example.test>"},
                {"name": "To", "value": "mailbox@example.test"},
                {"name": "Subject", "value": "Test thread"},
            ],
            "body": {"data": urlsafe_b64encode(content.encode()).decode().rstrip("=")},
        },
    }


async def test_first_sync_imports_full_thread_and_advances_after_all_pages() -> None:
    cipher = Fernet(Fernet.generate_key())
    lease = make_lease(cipher)
    dao, connection = make_dao(lease)
    now = datetime.now(UTC)
    page_tokens: list[str | None] = []
    thread_calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal thread_calls
        if request.url.host == "oauth2.googleapis.com":
            fields = parse_qs(request.content.decode())
            assert fields["grant_type"] == ["refresh_token"]
            assert fields["refresh_token"] == ["refresh-token"]
            return httpx.Response(200, json={"access_token": "read-only"})
        assert request.headers["Authorization"] == "Bearer read-only"
        if request.url.path.endswith("/messages"):
            query = request.url.params["q"].split()
            lower = int(query[0].removeprefix("after:"))
            upper = int(query[1].removeprefix("before:"))
            assert upper - lower == 30 * 86400 + 1
            assert request.url.params["includeSpamTrash"] == "false"
            token = request.url.params.get("pageToken")
            page_tokens.append(token)
            assert connection.synced_through_at == lease.synced_through_at
            payload = {"messages": [{"id": "recent", "threadId": "thread-1"}]}
            if token is None:
                payload["nextPageToken"] = "second"
            return httpx.Response(200, json=payload)
        thread_calls += 1
        assert request.url.params["format"] == "full"
        return httpx.Response(200, json={
            "id": "thread-1",
            "messages": [
                message(
                    "recent", now - timedelta(days=1),
                    "<p>New &amp; visible</p><script>hidden</script>",
                    mime="text/html",
                ),
                message("old", now - timedelta(days=80), "Old but in the thread"),
                message(
                    "draft", now - timedelta(days=1), "Excluded", labels=("DRAFT",),
                ),
            ],
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        service = GmailSyncService(
            dao, GmailClient(http), cipher, timedelta(minutes=1),
        )
        service._claim_due = AsyncMock(return_value=lease)
        assert await service.run_next()

    assert page_tokens == [None, "second"]
    assert thread_calls == 1
    dao.upsert_thread.assert_awaited_once()
    _, _, imported, _ = dao.upsert_thread.await_args.args
    assert [item.gmail_message_id for item in imported.messages] == ["old", "recent"]
    assert imported.messages[1].body == "New & visible"
    assert imported.client_email == "client@example.test"
    assert connection.last_success_at is not None
    assert connection.status == GmailConnectionStatus.CONNECTED


async def test_incremental_sync_keeps_cursor_on_failed_page() -> None:
    cipher = Fernet(Fernet.generate_key())
    cursor = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
    lease = make_lease(cipher, cursor)
    dao, connection = make_dao(lease)

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "access"})
        if request.url.params.get("pageToken"):
            return httpx.Response(429, headers={"Retry-After": "150"})
        lower = int(request.url.params["q"].split()[0].removeprefix("after:"))
        assert lower == int(cursor.timestamp()) - 301
        return httpx.Response(200, json={"nextPageToken": "next"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        service = GmailSyncService(
            dao, GmailClient(http), cipher, timedelta(minutes=1),
        )
        service._claim_due = AsyncMock(return_value=lease)
        assert await service.run_next()

    assert connection.synced_through_at == lease.synced_through_at
    assert connection.status == GmailConnectionStatus.SYNC_ERROR
    assert connection.next_sync_at - datetime.now(UTC) > timedelta(seconds=140)


async def test_revoked_refresh_token_pauses_sync_until_reauth() -> None:
    cipher = Fernet(Fernet.generate_key())
    lease = make_lease(cipher)
    dao, connection = make_dao(lease)

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "oauth2.googleapis.com"
        return httpx.Response(400, json={"error": "invalid_grant"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        service = GmailSyncService(
            dao, GmailClient(http), cipher, timedelta(minutes=1),
        )
        service._claim_due = AsyncMock(return_value=lease)
        assert await service.run_next()

    assert connection.synced_through_at == lease.synced_through_at
    assert connection.status == GmailConnectionStatus.REAUTH_REQUIRED
    assert connection.next_sync_at is None
