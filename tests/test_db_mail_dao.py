import asyncio
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db.dao.db_mail.draft import DraftDAO
from app.db.dao.db_mail.raw_email import RawEmailDAO
from app.db.dao.db_mail.thread import ThreadDAO
from app.db.dao.rag.email_chunk import EmailChunkDAO
from app.db.enums import AccountSource, GmailConnectionStatus
from app.db.models import GmailAccount, GmailConnection, Thread, User
from app.dto.db_mail import (
    DraftWrite,
    EmailWrite,
    MailFilters,
    MailSearchCriteria,
    ThreadWrite,
)
from app.dto.rag import IndexedChunk

pytestmark = pytest.mark.skipif(
    not os.environ.get("EMAIL_RAG_TEST_DB_URL"),
    reason="Requires a dedicated PostgreSQL database",
)


@dataclass(frozen=True)
class MailContext:
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]
    owner_id: UUID
    other_owner_id: UUID
    account_id: UUID
    other_account_id: UUID
    demo_account_id: UUID


@pytest.fixture
async def mail_context() -> AsyncIterator[MailContext]:
    engine = create_async_engine(os.environ["EMAIL_RAG_TEST_DB_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    context = MailContext(engine, sessions, uuid4(), uuid4(), uuid4(), uuid4(), uuid4())
    account_ids = (
        context.account_id, context.other_account_id, context.demo_account_id,
    )
    try:
        async with sessions.begin() as session:
            session.add_all([
                User(id=context.owner_id, email=f"{context.owner_id}@example.test"),
                User(
                    id=context.other_owner_id,
                    email=f"{context.other_owner_id}@example.test",
                ),
            ])
            await session.flush()
            session.add_all([
                GmailAccount(
                    id=context.account_id, owner_id=context.owner_id,
                    name="Work", gmail_email="manager@example.test",
                ),
                GmailAccount(
                    id=context.other_account_id, owner_id=context.other_owner_id,
                    name="Other", gmail_email="other@example.test",
                ),
                GmailAccount(
                    id=context.demo_account_id, owner_id=context.owner_id, name="Demo",
                ),
            ])
            await session.flush()
            session.add(GmailConnection(
                gmail_account_id=context.account_id,
                status=GmailConnectionStatus.CONNECTED,
                synced_through_at=datetime.now(UTC),
            ))
        yield context
    finally:
        async with sessions.begin() as session:
            await session.execute(
                delete(Thread).where(Thread.account_id.in_(account_ids)),
            )
            await session.execute(
                delete(GmailAccount).where(GmailAccount.id.in_(account_ids)),
            )
            await session.execute(delete(User).where(User.id.in_((
                context.owner_id, context.other_owner_id,
            ))))
        await engine.dispose()


def make_thread(account_id: UUID) -> ThreadWrite:
    return ThreadWrite(
        thread_id=uuid4(), account_source=AccountSource.GMAIL,
        account_id=account_id, external_thread_id="project-x",
        subject="Project X", client_email="client@example.test",
    )


def make_email(thread: ThreadWrite) -> EmailWrite:
    return EmailWrite(
        email_id=uuid4(), thread_id=thread.thread_id,
        account_source=thread.account_source, account_id=thread.account_id,
        message_id="agreement", sender="client@example.test",
        recipient="manager@example.test", date=datetime.now(UTC),
        subject="Project X", body="Delivery agreed for 22 November.",
    )


async def test_mail_access_read_search_and_draft_replay(
    mail_context: MailContext,
) -> None:
    ctx = mail_context
    threads = ThreadDAO(ctx.sessions)
    emails = RawEmailDAO(ctx.sessions)
    drafts = DraftDAO(ctx.sessions)
    thread = make_thread(ctx.account_id)
    await threads.upsert_thread(thread)
    await threads.upsert_thread(thread)
    email = make_email(thread)
    earlier = replace(
        email, email_id=uuid4(), message_id="proposal",
        date=email.date - timedelta(days=1),
    )
    await emails.insert_email(email)
    await emails.insert_email(earlier)
    await emails.insert_email(email)

    details = await threads.get_thread(thread.thread_id, owner_id=ctx.owner_id)
    assert details is not None
    assert details.mailbox_email == "manager@example.test"
    assert [message.id for message in details.messages] == [
        str(earlier.email_id), str(email.email_id),
    ]
    assert await emails.get_email(
        email.email_id, owner_id=ctx.owner_id,
    ) == details.messages[-1]
    assert await emails.get_email(email.email_id, owner_id=ctx.other_owner_id) is None
    assert len(await emails.get_thread_emails(
        thread.thread_id, owner_id=ctx.owner_id,
    )) == 2
    criteria = MailSearchCriteria(words="Project X")
    assert len(await emails.search_emails(criteria, owner_id=ctx.owner_id)) == 2
    assert not await emails.search_emails(criteria, owner_id=ctx.other_owner_id)
    assert not await emails.search_emails(criteria)
    assert await threads.get_thread(
        thread.thread_id, owner_id=ctx.other_owner_id,
    ) is None
    assert await threads.thread_activity(
        [thread.thread_id], owner_id=ctx.owner_id,
    ) == {thread.thread_id: email.date}

    draft = DraftWrite(
        thread_id=thread.thread_id, recipient=email.sender,
        subject="Re: Project X", text_content="Confirmed.", operation_id=uuid4(),
    )
    results = await asyncio.gather(*(
        drafts.save_draft(draft, owner_id=ctx.owner_id) for _ in range(2)
    ))
    assert results[0] is not None and results[0] == results[1]
    assert await drafts.draft_for_operation(
        draft.operation_id, owner_id=ctx.owner_id,
    ) == results[0]
    assert await drafts.save_draft(draft, owner_id=ctx.other_owner_id) is None
    assert len(await drafts.list_drafts(owner_id=ctx.owner_id)) == 1
    assert not await drafts.list_drafts(owner_id=ctx.other_owner_id)

    async with ctx.sessions.begin() as session:
        connection = await session.get(GmailConnection, ctx.account_id)
        connection.status = GmailConnectionStatus.DISCONNECTED
    assert await threads.get_thread(thread.thread_id, owner_id=ctx.owner_id) is None
    assert await drafts.save_draft(draft, owner_id=ctx.owner_id) is None
    assert not await emails.search_emails(criteria, owner_id=ctx.owner_id)


async def test_mail_feed_paginates_ties_and_scopes_results(
    mail_context: MailContext,
) -> None:
    ctx = mail_context
    threads = ThreadDAO(ctx.sessions)
    emails = RawEmailDAO(ctx.sessions)
    thread = make_thread(ctx.account_id)
    await threads.upsert_thread(thread)
    template = make_email(thread)
    records = [
        replace(template, email_id=uuid4(), message_id=str(index))
        for index in range(13)
    ]
    for record in records:
        await emails.insert_email(record)
    await emails.insert_email(replace(
        template,
        email_id=uuid4(),
        message_id="earlier",
        date=template.date - timedelta(days=1),
    ))

    filters = MailFilters(
        words="delivery",
        sender="client",
        participant="manager@example.test",
        start_date=template.date.date(),
        end_date=template.date.date(),
    )
    first = await emails.list_page(
        filters, owner_id=ctx.owner_id, account_id=ctx.account_id, cursor=None, limit=10,
    )
    assert first.next_cursor is not None
    rest = await emails.list_page(
        filters,
        owner_id=ctx.owner_id,
        account_id=ctx.account_id,
        cursor=first.next_cursor,
        limit=10,
    )
    assert rest.next_cursor is None
    expected = sorted((record.email_id for record in records), reverse=True)
    assert [item.email_id for item in first.items + rest.items] == list(map(str, expected))

    hidden = await emails.list_page(
        MailFilters(),
        owner_id=ctx.other_owner_id,
        account_id=ctx.account_id,
        cursor=None,
        limit=10,
    )
    assert not hidden.items


async def test_mail_integrity_and_demo_access(mail_context: MailContext) -> None:
    ctx = mail_context
    threads = ThreadDAO(ctx.sessions)
    emails = RawEmailDAO(ctx.sessions)
    thread = make_thread(ctx.demo_account_id)
    await threads.upsert_thread(thread)
    email = make_email(thread)
    await emails.insert_email(email)
    assert await threads.get_thread(thread.thread_id) is not None

    with pytest.raises(ValueError, match="аккаунт не найден"):
        await threads.upsert_thread(make_thread(uuid4()))
    with pytest.raises(ValueError, match="аккаунт не найден"):
        await emails.insert_email(replace(email, account_id=uuid4()))
    with pytest.raises(IntegrityError):
        await threads.upsert_thread(replace(thread, thread_id=uuid4()))
    with pytest.raises(IntegrityError):
        await emails.insert_email(replace(email, email_id=uuid4()))
    with pytest.raises(IntegrityError):
        await emails.insert_email(replace(
            email, email_id=uuid4(), account_id=ctx.other_account_id,
        ))
    with pytest.raises(ValueError, match="другому аккаунту"):
        await threads.upsert_thread(replace(thread, account_id=ctx.other_account_id))


async def test_source_isolation_and_composite_constraints(
    mail_context: MailContext,
) -> None:
    ctx = mail_context
    # Имитируем будущий провайдер только в изолированной тестовой БД.
    async with ctx.engine.connect() as connection:
        connection = await connection.execution_options(isolation_level="AUTOCOMMIT")
        await connection.execute(text(
            "ALTER TYPE account_source ADD VALUE IF NOT EXISTS 'outlook'",
        ))

    threads = ThreadDAO(ctx.sessions)
    emails = RawEmailDAO(ctx.sessions)
    gmail_thread = make_thread(ctx.account_id)
    await threads.upsert_thread(gmail_thread)
    gmail_email = make_email(gmail_thread)
    await emails.insert_email(gmail_email)
    outlook_id = uuid4()
    outlook_email_id = uuid4()
    async with ctx.sessions.begin() as session:
        await session.execute(text("""
            INSERT INTO threads (
                id, account_source, account_id, external_thread_id,
                subject, client_email
            ) VALUES (:id, 'outlook', :account, 'project-x', 'Project X', 'client')
        """), {"id": outlook_id, "account": ctx.account_id})
        await session.execute(text("""
            INSERT INTO raw_emails (
                id, thread_id, account_source, account_id, message_id,
                sender, recipient, date, subject, body
            ) VALUES (
                :id, :thread, 'outlook', :account, 'agreement',
                'client', 'manager', now(), 'Project X', 'Project X'
            )
        """), {
            "id": outlook_email_id, "thread": outlook_id, "account": ctx.account_id,
        })
    assert await threads.get_thread(outlook_id, owner_id=ctx.owner_id) is None
    matches = await emails.search_emails(
        MailSearchCriteria(words="Project X"), owner_id=ctx.owner_id,
    )
    assert [match.email_id for match in matches] == [str(gmail_email.email_id)]
    chunks = EmailChunkDAO(ctx.sessions)
    jobs = await chunks.pending_jobs(datetime.now(UTC) + timedelta(hours=1))
    assert {job.email_id for job in jobs} == {gmail_email.email_id}
    assert await chunks.replace_chunks(jobs[0], [IndexedChunk(
        0, "Project X", [1.0] + [0.0] * 1023,
    )])
    assert await DraftDAO(ctx.sessions).save_draft(DraftWrite(
        thread_id=outlook_id, recipient="client", subject="Reply", text_content="Test",
    ), owner_id=ctx.owner_id) is None
    with pytest.raises(IntegrityError):
        await emails.insert_email(replace(
            gmail_email, email_id=uuid4(), thread_id=outlook_id,
            message_id="wrong-source",
        ))

    # Без FK на Gmail таблица может хранить аккаунт другого провайдера.
    async with ctx.sessions() as session:
        columns = await session.execute(text("""
            SELECT constraint_name FROM information_schema.table_constraints
            WHERE table_name = 'threads' AND constraint_type = 'FOREIGN KEY'
        """))
        assert not columns.all()
    async with ctx.sessions.begin() as session:
        await session.execute(delete(Thread).where(Thread.id == outlook_id))
