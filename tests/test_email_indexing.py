from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx

from app.agent.nodes.prepare_result import _model_context, _recipient
from app.agent.nodes.search import _select_thread
from app.configs.rag_worker import RagWorkerConfig
from app.db.dao.db_mail.raw_email import RawEmailDAO
from app.db.dao.rag.email_chunk import EmailChunkDAO
from app.dto.db_mail import (
    MailMessage,
    MailSearchCriteria,
    MailSnippet,
    MailThreadDetails,
)
from app.dto.rag import EmailIndexingJob
from app.external_api_clients.embedding_client import EmbeddingClient
from app.services.rag.ingestion.email.service import EmailIngestionService
from app.services.rag.retrieval.email.service import EmailRetrievalService


async def test_indexes_forwarded_source_without_llm_and_preserves_short_replies():
    dao = AsyncMock(spec=EmailChunkDAO)
    dao.replace_chunks.return_value = True
    embedding = AsyncMock(spec=EmbeddingClient)
    embedding.get_embeddings.side_effect = lambda texts: [[0.1] * 1024 for _ in texts]
    service = EmailIngestionService(dao, embedding)
    job = EmailIndexingJob(
        uuid4(), uuid4(), 1, datetime.now(UTC), "Project X",
        "See below\n--- Forwarded message ---\nDelivery agreed for 20 November.",
    )
    assert await service.process_email(job)
    texts = embedding.get_embeddings.await_args.args[0]
    assert "20 November" in "\n".join(texts)
    saved_job, chunks = dao.replace_chunks.await_args.args
    assert saved_job == job
    assert len(chunks) == len(texts)

    short = EmailIndexingJob(
        uuid4(), job.account_id, 1, job.updated_at, "Re: Project X", "Да",
    )
    await service.process_email(short)
    assert "Да" in embedding.get_embeddings.await_args.args[0][0]


def test_selects_latest_thread_even_when_matching_message_is_old():
    now = datetime.now(UTC)
    newest_thread = str(uuid4())
    matches = [
        MailSnippet(
            str(uuid4()), str(uuid4()), "Project X", "client@example.test",
            now - timedelta(days=1), "Project X", now - timedelta(days=1),
        ),
        MailSnippet(
            str(uuid4()), newest_thread, "Project X", "client@example.test",
            now - timedelta(days=10), "Project X", now,
        ),
    ]
    update = _select_thread(matches, latest=True)
    assert update["thread_id"] == UUID(newest_thread)


async def test_hybrid_search_deduplicates_and_falls_back_when_embedder_fails():
    dao = AsyncMock(spec=RawEmailDAO)
    chunk_dao = AsyncMock(spec=EmailChunkDAO)
    embedding = AsyncMock(spec=EmbeddingClient)
    owner = uuid4()
    mail = MailSnippet(
        str(uuid4()), str(uuid4()), "Project X", "client@example.test",
        datetime.now(UTC), "Delivery postponed",
    )
    dao.search_emails.return_value = [mail]
    chunk_dao.search.return_value = [mail]
    embedding.get_embedding.return_value = [0.1] * 1024
    service = EmailRetrievalService(dao, chunk_dao, embedding)
    criteria = MailSearchCriteria(words="Project X")
    assert await service.search(criteria, owner_id=owner) == [mail]
    assert chunk_dao.search.await_args.args[2] == owner
    embedding.get_embedding.side_effect = httpx.ConnectError("offline")
    assert await service.search(criteria, owner_id=owner) == [mail]


def test_draft_targets_last_incoming_and_context_keeps_earlier_agreement():
    now = datetime.now(UTC)
    thread_id = str(uuid4())
    old = MailMessage(
        str(uuid4()), thread_id, "client@example.test", "manager@example.test",
        now - timedelta(days=10), "Project X", "Agreed delivery 20 November.",
    )
    latest = MailMessage(
        str(uuid4()), thread_id, "client@example.test", "manager@example.test",
        now - timedelta(minutes=2), "Re: Project X", "Please confirm.",
    )
    outgoing = MailMessage(
        str(uuid4()), thread_id, "manager@example.test", "client@example.test",
        now, "Re: Project X", "Checking.",
    )
    thread = MailThreadDetails(
        thread_id, "Project X", "client@example.test",
        [old, latest, outgoing], "manager@example.test",
    )
    assert _recipient(thread, None) == "client@example.test"
    context = _model_context(
        {"request": "List deadlines and draft", "rag_chunks": []},
        thread, "client@example.test",
    )
    assert old.id in context
    assert f'"reply_to_email_id": "{latest.id}"' in context


def test_delay_can_be_configured(monkeypatch):
    monkeypatch.setenv("RAG_WORKER_INDEXING_DELAY_MINUTES", "0")
    assert RagWorkerConfig().indexing_delay_minutes == 0


async def test_very_long_heading_stays_within_embedding_fragment_limit():
    dao = AsyncMock(spec=EmailChunkDAO)
    embedding = AsyncMock(spec=EmbeddingClient)
    embedding.get_embeddings.side_effect = lambda texts: [[0.1] * 1024 for _ in texts]
    job = EmailIndexingJob(
        uuid4(), uuid4(), 0, datetime.now(UTC), "Long email",
        "# " + "x" * 4000 + "\n\nA paragraph.",
    )
    await EmailIngestionService(dao, embedding).process_email(job)
    fragments = embedding.get_embeddings.await_args.args[0]
    assert all(len(fragment) <= 1402 for fragment in fragments)
