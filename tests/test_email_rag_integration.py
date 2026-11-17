"""Run against an empty migrated PostgreSQL selected by EMAIL_RAG_TEST_DB_URL."""

from datetime import UTC, datetime, timedelta
import json
import os
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

from cryptography.fernet import Fernet
import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent.service import AgentService
from app.db.dao.db_mail.draft import DraftDAO
from app.db.dao.db_mail.raw_email import RawEmailDAO
from app.db.dao.db_mail.thread import ThreadDAO
from app.db.dao.gmail.gmail import GmailDAO
from app.db.dao.rag.document_chunk import DocumentChunkDAO
from app.db.dao.rag.email_chunk import EmailChunkDAO
from app.db.enums import GmailConnectionStatus
from app.db.models import (
    Draft, EmailChunk, GmailAccount, GmailConnection, RawEmail, User,
)
from app.dto.db_mail import DraftWrite, MailSearchCriteria
from app.dto.gmail import ImportedGmailMessage, ImportedGmailThread
from app.dto.rag import IndexedChunk
from app.external_api_clients.embedding_client import EmbeddingClient
from app.external_api_clients.llm_client import LLMClient
from app.external_api_clients.schemas import LLMResponse
from app.services.db_mail.draft import DraftService
from app.services.db_mail.thread import ThreadService
from app.services.gmail.gmail_sync_service import GmailSyncService
from app.services.rag.ingestion.email.service import EmailIngestionService
from app.services.rag.retrieval.document.service import DocumentRetrievalService
from app.services.rag.retrieval.email.service import EmailRetrievalService


@pytest.mark.skipif(
    not os.environ.get("EMAIL_RAG_TEST_DB_URL"),
    reason="Requires a dedicated PostgreSQL database",
)
async def test_import_index_search_read_draft_and_owner_isolation():
    engine = create_async_engine(os.environ["EMAIL_RAG_TEST_DB_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        await _exercise_pipeline(sessions)
    finally:
        await engine.dispose()


async def _exercise_pipeline(sessions):
    now = datetime.now(UTC)
    vector = [1.0] + [0.0] * 1023
    async with sessions.begin() as session:
        owner = User(email="rag-owner@example.test")
        other = User(email="rag-other@example.test")
        session.add_all([owner, other])
        await session.flush()
        account = GmailAccount(
            owner_id=owner.id, name="Work", gmail_email="manager@example.test",
        )
        session.add(account)
        await session.flush()
        session.add(GmailConnection(
            gmail_account_id=account.id, client_id="test",
            client_secret_ciphertext="test", refresh_token_ciphertext="test",
            status=GmailConnectionStatus.CONNECTED, next_sync_at=now,
            synced_through_at=now,
        ))

    sync = GmailSyncService(
        GmailDAO(sessions), MagicMock(), Fernet(Fernet.generate_key()),
        timedelta(minutes=1),
    )
    lease = await sync._claim_due(now)
    source = ImportedGmailThread(
        "latest-thread", "Project X", "client@example.test",
        [
            ImportedGmailMessage(
                "proposal", "manager@example.test", "client@example.test",
                now - timedelta(days=5), "Project X", "Delivery proposed for 20 Nov.",
            ),
            ImportedGmailMessage(
                "agreement", "client@example.test", "manager@example.test",
                now - timedelta(minutes=2), "Confirmed",
                "Agreed. Please confirm 22 Nov.",
            ),
        ],
    )
    imported_at = now
    await sync._save_thread(lease, source, imported_at)
    await sync._save_thread(
        lease,
        ImportedGmailThread(
            "older-thread", "Project X", "client@example.test",
            [ImportedGmailMessage(
                "older-match", "client@example.test", "manager@example.test",
                now - timedelta(days=1), "Project X", "An earlier conversation.",
            )],
        ),
        imported_at,
    )
    await sync._complete(lease, now, now, now)
    chunks = EmailChunkDAO(sessions)
    embedding = AsyncMock(spec=EmbeddingClient)
    embedding.get_embedding.return_value = vector
    embedding.get_embeddings.side_effect = lambda texts: [vector for _ in texts]
    ingestion = EmailIngestionService(chunks, embedding)
    assert not await chunks.pending_jobs(now - timedelta(minutes=30))
    jobs = await chunks.pending_jobs(now + timedelta(minutes=1))
    assert len(jobs) == 3
    for job in jobs:
        assert await ingestion.process_email(job)
    assert not await chunks.pending_jobs(now)

    # Replay of identical Gmail data must not postpone or repeat indexing.
    lease = await sync._claim_due(now + timedelta(seconds=1))
    await sync._save_thread(lease, source, now)
    assert not await chunks.pending_jobs(now)
    await sync._complete(lease, now, now + timedelta(seconds=1), now)

    thread_dao = ThreadDAO(sessions)
    draft_dao = DraftDAO(sessions)
    email_search = EmailRetrievalService(RawEmailDAO(sessions), chunks, embedding)
    threads = ThreadService(thread_dao)
    drafts = DraftService(draft_dao)
    criteria = MailSearchCriteria(words="Project X")
    matches = await email_search.search(criteria, owner_id=owner.id)
    activity = await threads.thread_activity(matches, owner_id=owner.id)
    newest = max(activity, key=lambda item: item.thread_last_date)
    thread = await threads.get_thread(UUID(newest.thread_id), owner_id=owner.id)
    assert len(thread.messages) == 2
    target_id = thread.messages[-1].id
    assert thread.messages[-1].body == "Agreed. Please confirm 22 Nov."

    # A different owner cannot search, read or save using a known thread UUID.
    assert not await email_search.search(criteria, owner_id=other.id)
    assert await thread_dao.get_thread(
        UUID(thread.thread_id), owner_id=other.id,
    ) is None
    assert await draft_dao.save_draft(DraftWrite(
        thread_id=UUID(thread.thread_id), recipient="client@example.test",
        subject="Subject", text_content="Body",
    ), owner_id=other.id) is None

    # Date and participant constraints apply to semantic matches too.
    assert not await chunks.search(
        MailSearchCriteria(words="Project X", participant="stranger@example.test"),
        vector, owner.id, 5,
    )
    assert not await chunks.search(
        MailSearchCriteria(
            words="Project X", start_date=(now + timedelta(days=1)).date(),
        ),
        vector, owner.id, 5,
    )

    documents = DocumentChunkDAO(sessions)
    await documents.replace_chunks(
        "delivery", "Delivery terms",
        [IndexedChunk(0, "Delivery is subject to signed approval.", vector)],
    )
    rag = DocumentRetrievalService(documents, embedding)
    llm = MagicMock(spec=LLMClient)
    llm.chat = AsyncMock()

    def reply(**kwargs):
        tools = kwargs.get("tools") or []
        name = tools[0]["function"]["name"] if tools else None
        if name == "search_emails":
            args = {"words": "Project X", "thread_selection": "latest"}
        elif name == "read_thread":
            args = {"thread_id": thread.thread_id}
        elif name == "create_draft":
            payload = kwargs["messages"][-1]["content"]
            assert "22 Nov" in payload and "signed approval" in payload
            assert target_id in payload
            args = {
                "thread_id": thread.thread_id, "recipient": "client@example.test",
                "subject": "Re: Project X",
                "text": "Delivery on 22 Nov, subject to signed approval.",
            }
        else:
            if "task" in kwargs.get("response_format", {}).get(
                "json_schema", {},
            ).get("schema", {}).get("properties", {}):
                return LLMResponse(content='{"task": "draft"}')
            return LLMResponse(content=json.dumps({
                "response": "Delivery agreed for 22 Nov.",
                "email_ids": [target_id], "document_ids": ["delivery"],
            }))
        return LLMResponse(tool_calls=[{"id": name, "name": name, "args": args}])

    llm.chat.side_effect = reply
    result = await AgentService(llm, email_search, threads, drafts, rag).chat(
        "Find latest Project X conversation, list deadlines and draft a reply.",
        user_id=owner.id,
    )
    assert result.draft_id and result.used_email_ids == [target_id]
    assert result.used_document_ids == ["delivery"]
    assert await drafts.draft_for_operation(UUID(result.run_id), owner.id) == result.draft_id
    assert await drafts.draft_for_operation(UUID(result.run_id), other.id) is None
    async with sessions() as session:
        draft = await session.get(Draft, UUID(result.draft_id))
        assert draft.thread_id == UUID(thread.thread_id)
        assert draft.recipient == "client@example.test"

    # An update invalidates old chunks, then atomically replaces them after delay.
    stale = jobs[0]
    async with sessions.begin() as session:
        await session.execute(
            update(RawEmail).where(RawEmail.id == stale.email_id)
            .values(
                body="Changed agreement", rag_updated_at=now + timedelta(seconds=2),
            ),
        )
    assert not await chunks.replace_chunks(stale, [])
    assert not await chunks.pending_jobs(now - timedelta(minutes=30))
    due = await chunks.pending_jobs(now + timedelta(minutes=1))
    assert len(due) == 1
    assert await ingestion.process_email(due[0])
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(EmailChunk)) == 3

    # Disconnect immediately removes even previously built semantic candidates.
    async with sessions.begin() as session:
        await session.execute(update(GmailConnection).values(
            status=GmailConnectionStatus.DISCONNECTED,
        ))
    assert not await email_search.search(criteria, owner_id=owner.id)
    assert not await chunks.pending_jobs(now + timedelta(hours=1))
