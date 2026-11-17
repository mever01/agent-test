import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from random import uniform
from uuid import UUID, uuid4

import httpx
from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr, ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.dao.gmail.gmail import GmailDAO
from app.db.enums import GmailConnectionStatus
from app.dto.gmail import (
    GmailConnectionData,
    GmailSyncLease,
    ImportedGmailMessage,
    ImportedGmailThread,
)
from app.external_api_clients.gmail.client import (
    GmailClient,
    GmailReauthRequired,
    GmailRequestError,
)
from app.external_api_clients.gmail.schemas import GmailPartBody
from app.services.exceptions import GmailLeaseLost
from app.services.gmail.gmail_message_parser import (
    is_importable,
    message_date,
    parse_message,
)

logger = logging.getLogger(__name__)

FIRST_IMPORT_WINDOW = timedelta(days=30)
SEARCH_OVERLAP = timedelta(minutes=5)
RETRY_DELAY_SECONDS = 60
_FULL_THREAD_INTERVAL = 1.5
_SYNCABLE_STATUSES = (
    GmailConnectionStatus.CONNECTED,
    GmailConnectionStatus.SYNCING,
    GmailConnectionStatus.SYNC_ERROR,
)


class GmailSyncService:
    def __init__(
        self,
        dao: GmailDAO,
        client: GmailClient,
        cipher: Fernet,
        interval: timedelta,
        *,
        lease_duration: timedelta = timedelta(minutes=2),
    ) -> None:
        self._dao = dao
        self._lease_duration = lease_duration
        self._client = client
        self._cipher = cipher
        self._interval = interval

    async def _claim_due(self, now: datetime) -> GmailSyncLease | None:
        async with self._dao.transaction() as session:
            selected = await self._dao.lock_due_connection(
                session, now, _SYNCABLE_STATUSES,
            )
            if selected is None:
                return None
            connection, gmail_email = selected
            token = uuid4()
            connection.lease_token = token
            connection.lease_expires_at = now + self._lease_duration
            connection.status = GmailConnectionStatus.SYNCING
            await self._dao.save_connection(session, connection)
            return GmailSyncLease(
                account_id=connection.gmail_account_id,
                gmail_email=gmail_email,
                client_id=connection.client_id,
                client_secret_ciphertext=connection.client_secret_ciphertext,
                refresh_token_ciphertext=connection.refresh_token_ciphertext,
                synced_through_at=connection.synced_through_at,
                token=token,
                generation=connection.generation,
            )

    async def _locked_connection(
        self, session: AsyncSession, lease: GmailSyncLease, now: datetime,
    ) -> GmailConnectionData:
        connection = await self._dao.lock_sync_connection(session, lease, now)
        if connection is None:
            raise GmailLeaseLost
        return connection

    async def _renew(self, lease: GmailSyncLease, now: datetime) -> None:
        async with self._dao.transaction() as session:
            connection = await self._locked_connection(session, lease, now)
            connection.lease_expires_at = now + self._lease_duration
            await self._dao.save_connection(session, connection)

    async def _existing_message_ids(
        self, account_id: UUID, message_ids: list[str],
    ) -> set[str]:
        async with self._dao.transaction() as session:
            return await self._dao.existing_message_ids(
                session, account_id, message_ids,
            )

    async def _save_thread(
        self, lease: GmailSyncLease, thread: ImportedGmailThread, now: datetime,
    ) -> None:
        async with self._dao.transaction() as session:
            await self._dao.lock_account(session, lease.account_id)
            connection = await self._locked_connection(session, lease, now)
            connection.lease_expires_at = now + self._lease_duration
            await self._dao.save_connection(session, connection)
            thread_id = await self._dao.upsert_thread(
                session, lease.account_id, thread, now,
            )
            for offset in range(0, len(thread.messages), 200):
                await self._dao.upsert_messages(
                    session, lease.account_id, thread_id,
                    thread.messages[offset : offset + 200], now,
                )

    async def _complete(
        self, lease: GmailSyncLease, synced_through_at: datetime,
        now: datetime, next_sync_at: datetime,
    ) -> None:
        async with self._dao.transaction() as session:
            connection = await self._locked_connection(session, lease, now)
            connection.status = GmailConnectionStatus.CONNECTED
            connection.synced_through_at = synced_through_at
            connection.last_success_at = now
            connection.next_sync_at = next_sync_at
            connection.lease_expires_at = None
            connection.lease_token = None
            await self._dao.save_connection(session, connection)

    async def _fail(
        self, lease: GmailSyncLease, status: GmailConnectionStatus,
        now: datetime, next_sync_at: datetime | None,
    ) -> None:
        async with self._dao.transaction() as session:
            connection = await self._locked_connection(session, lease, now)
            connection.status = status
            connection.next_sync_at = next_sync_at
            connection.lease_expires_at = None
            connection.lease_token = None
            await self._dao.save_connection(session, connection)

    async def run_next(self) -> bool:
        lease = await self._claim_due(datetime.now(UTC))
        if lease is None:
            return False
        started = datetime.now(UTC)
        upper = started.replace(microsecond=0)
        if lease.synced_through_at is not None:
            upper = max(upper, lease.synced_through_at)
        try:
            imported = await self._import_mail(lease, upper)
            now = datetime.now(UTC)
            await self._complete(lease, upper, now, now + self._interval)
            logger.info(
                "Gmail sync completed account_id=%s messages=%s duration_s=%.2f",
                lease.account_id, imported, (now - started).total_seconds(),
            )
        except GmailLeaseLost:
            logger.info("Gmail sync lease lost account_id=%s", lease.account_id)
        except GmailReauthRequired as exc:
            await self._record_failure(
                lease, GmailConnectionStatus.REAUTH_REQUIRED, exc,
            )
        except (
            GmailRequestError, httpx.RequestError, InvalidToken, ValidationError,
            ValueError, OverflowError, SQLAlchemyError,
        ) as exc:
            await self._record_failure(lease, GmailConnectionStatus.SYNC_ERROR, exc)
        return True

    async def _record_failure(
        self, lease: GmailSyncLease, status: GmailConnectionStatus, error: Exception,
    ) -> None:
        now = datetime.now(UTC)
        next_sync_at = None
        if status == GmailConnectionStatus.SYNC_ERROR:
            retry_at = error.retry_at if isinstance(error, GmailRequestError) else None
            if retry_at and retry_at > now:
                next_sync_at = retry_at
            else:
                delay = RETRY_DELAY_SECONDS + uniform(0, 15)
                next_sync_at = now + timedelta(seconds=delay)
        try:
            await self._fail(lease, status, now, next_sync_at)
        except GmailLeaseLost:
            return
        logger.warning(
            "Gmail sync paused account_id=%s status=%s error=%s http_status=%s",
            lease.account_id, status.value, type(error).__name__,
            error.status_code if isinstance(error, GmailRequestError) else None,
        )

    async def _import_mail(self, lease: GmailSyncLease, upper: datetime) -> int:
        lower = (
            lease.synced_through_at - SEARCH_OVERLAP
            if lease.synced_through_at is not None else upper - FIRST_IMPORT_WINDOW
        )
        client_secret = SecretStr(
            self._cipher.decrypt(lease.client_secret_ciphertext).decode(),
        )
        refresh_token = SecretStr(
            self._cipher.decrypt(lease.refresh_token_ciphertext).decode(),
        )
        access_token: SecretStr | None = None

        async def refresh_access() -> SecretStr:
            await self._renew(lease, datetime.now(UTC))
            tokens = await self._client.refresh(
                lease.client_id, client_secret, refresh_token,
            )
            return tokens.access_token

        async def request[T](operation: Callable[[SecretStr], Awaitable[T]]) -> T:
            nonlocal access_token
            if access_token is None:
                access_token = await refresh_access()
            await self._renew(lease, datetime.now(UTC))
            try:
                return await operation(access_token)
            except GmailRequestError as exc:
                if exc.status_code != 401:
                    raise
            access_token = await refresh_access()
            await self._renew(lease, datetime.now(UTC))
            return await operation(access_token)

        async def load_text_part(message_id: str, attachment_id: str) -> GmailPartBody:
            try:
                return await request(
                    lambda token: self._client.get_text_part(
                        token, message_id, attachment_id,
                    )
                )
            except GmailRequestError as exc:
                if exc.status_code != 404:
                    raise
                return GmailPartBody()

        total = 0
        page_token = None
        loaded_threads: set[str] = set()
        seen_tokens: set[str] = set()
        last_fetch: float | None = None
        loop = asyncio.get_running_loop()
        while True:
            page = await request(lambda token: self._client.list_messages(
                token, after=lower, before=upper, page_token=page_token,
            ))
            existing = await self._existing_message_ids(
                lease.account_id, [message.id for message in page.messages],
            )
            candidates: dict[str, set[str]] = {}
            for message in page.messages:
                if (
                    message.id not in existing
                    and message.thread_id not in loaded_threads
                ):
                    candidates.setdefault(message.thread_id, set()).add(message.id)

            for thread_id, candidate_ids in candidates.items():
                if last_fetch is not None:
                    delay = _FULL_THREAD_INTERVAL - (loop.time() - last_fetch)
                    if delay > 0:
                        await asyncio.sleep(delay)
                last_fetch = loop.time()
                try:
                    thread = await request(
                        lambda token: self._client.get_thread(token, thread_id),
                    )
                except GmailRequestError as exc:
                    if exc.status_code != 404:
                        raise
                    loaded_threads.add(thread_id)
                    continue
                if thread.id != thread_id:
                    raise ValueError("Unexpected Gmail thread ID")
                mail = [item for item in thread.messages if is_importable(item)]
                if not any(
                    item.id in candidate_ids and lower <= message_date(item) < upper
                    for item in mail
                ):
                    continue
                mail.sort(key=lambda item: (item.internal_date_ms, item.id))
                messages = [
                    await parse_message(message, lease.gmail_email, load_text_part)
                    for message in mail
                ]
                imported_thread = ImportedGmailThread(
                    thread_id,
                    messages[0].subject,
                    _client_address(messages, lease.gmail_email),
                    messages,
                )
                await self._save_thread(lease, imported_thread, datetime.now(UTC))
                loaded_threads.add(thread_id)
                total += len(messages)

            page_token = page.next_page_token
            if not page_token:
                return total
            if page_token in seen_tokens:
                raise ValueError("Gmail returned a repeated page token")
            seen_tokens.add(page_token)


def _client_address(messages: list[ImportedGmailMessage], mailbox: str) -> str:
    for message in messages:
        address = message.recipient if message.sender == mailbox else message.sender
        if address and address != mailbox:
            return address
    return mailbox
