import asyncio
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.dao.gmail.gmail import GmailDAO
from app.db.models import RawEmail, Thread, User
from app.dto.gmail import AuthorizedMailbox, ImportedGmailMessage, ImportedGmailThread
from app.external_api_clients.gmail.client import GmailClient
from app.services.exceptions import GmailConnectionConflict, GmailLeaseLost
from app.services.gmail.gmail_service import GmailService
from app.services.gmail.gmail_sync_service import GmailSyncService


@pytest.mark.skipif(
    not os.environ.get("EMAIL_RAG_TEST_DB_URL"),
    reason="Requires a dedicated PostgreSQL database",
)
async def test_gmail_dao_transactions_and_service_lifecycle() -> None:
    engine = create_async_engine(os.environ["EMAIL_RAG_TEST_DB_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        dao = GmailDAO(sessions)
        cipher = Fernet(Fernet.generate_key())
        client = AsyncMock(spec=GmailClient)
        oauth = GmailService(dao, client, cipher)
        async with dao.transaction() as session:
            owner = User(id=uuid4(), email="gmail-dao@example.test")
            session.add(owner)

        account = await oauth.create(owner.id, "Work")
        await oauth.configure(owner.id, account.id, "client", SecretStr("secret"))
        client.authorization_url.side_effect = (
            lambda client_id, state, challenge: f"https://example.test?state={state}"
        )
        authorization = await oauth.start(owner.id, account.id)
        state = parse_qs(urlsplit(authorization.url).query)["state"][0]

        attempts = await asyncio.gather(
            oauth._claim_attempt(state, authorization.browser_token),
            oauth._claim_attempt(state, authorization.browser_token),
        )
        assert sum(item is not None for item in attempts) == 1
        attempt = next(item for item in attempts if item is not None)
        await oauth._activate(
            attempt,
            AuthorizedMailbox(
                "box@example.test", [],
                cipher.encrypt(b"refresh-token").decode(),
            ),
        )

        sync = GmailSyncService(dao, client, cipher, timedelta(minutes=1))
        now = datetime.now(UTC)
        claims = await asyncio.gather(sync._claim_due(now), sync._claim_due(now))
        assert sum(item is not None for item in claims) == 1
        lease = next(item for item in claims if item is not None)
        imported = ImportedGmailThread(
            "thread", "Project X", "client@example.test",
            [
                ImportedGmailMessage(
                    str(index), "client@example.test", "box@example.test",
                    now, "Project X", f"Message {index}",
                )
                for index in range(201)
            ],
        )

        original_upsert = dao.upsert_messages

        async def fail_second_batch(
            session: AsyncSession,
            account_id: UUID,
            thread_id: UUID,
            messages: list[ImportedGmailMessage],
            imported_at: datetime,
        ) -> None:
            if len(messages) < 200:
                raise RuntimeError("Simulated second batch failure")
            await original_upsert(
                session, account_id, thread_id, messages, imported_at,
            )

        dao.upsert_messages = AsyncMock(side_effect=fail_second_batch)
        with pytest.raises(RuntimeError, match="second batch"):
            await sync._save_thread(lease, imported, now)
        dao.upsert_messages = original_upsert
        async with dao.transaction() as session:
            assert await session.scalar(select(func.count()).select_from(Thread).where(
                Thread.account_id == account.id,
            )) == 0
            assert await session.scalar(
                select(func.count()).select_from(RawEmail).where(
                    RawEmail.account_id == account.id,
                ),
            ) == 0

        await sync._save_thread(lease, imported, now)
        await sync._save_thread(lease, imported, now + timedelta(seconds=1))
        async with dao.transaction() as session:
            emails = list(await session.scalars(select(RawEmail).where(
                RawEmail.account_id == account.id,
            )))
            assert len(emails) == 201
            assert all(mail.rag_updated_at == now for mail in emails)

        changed = replace(
            imported,
            messages=[replace(imported.messages[0], body="Changed agreement")],
        )
        await sync._save_thread(lease, changed, now + timedelta(seconds=2))
        async with dao.transaction() as session:
            changed_ids = set(await session.scalars(
                select(RawEmail.message_id)
                .where(
                    RawEmail.account_id == account.id, RawEmail.rag_updated_at > now,
                ),
            ))
            assert changed_ids == {"0"}

        with pytest.raises(GmailLeaseLost):
            await sync._renew(lease, now + timedelta(minutes=3))

        # A callback claimed before disconnect cannot reactivate the connection.
        authorization = await oauth.start(owner.id, account.id)
        state = parse_qs(urlsplit(authorization.url).query)["state"][0]
        pending = await oauth._claim_attempt(state, authorization.browser_token)
        assert pending is not None
        await oauth.disconnect(owner.id, account.id)
        with pytest.raises(GmailLeaseLost):
            await sync._save_thread(lease, imported, now + timedelta(seconds=3))
        with pytest.raises(GmailConnectionConflict):
            await oauth._activate(
                pending,
                AuthorizedMailbox("box@example.test", [], "new-token"),
            )

        accounts = await oauth.list_accounts(owner.id)
        assert accounts[0].status.value == "disconnected"
    finally:
        await engine.dispose()
