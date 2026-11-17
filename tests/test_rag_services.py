import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.configs.rag_worker import RagWorkerConfig
from app.db.dao.db_mail.raw_email import RawEmailDAO
from app.db.dao.rag.document_chunk import DocumentChunkDAO
from app.db.dao.rag.email_chunk import EmailChunkDAO
from app.dto.db_mail import MailSearchCriteria, MailSnippet
from app.dto.rag import (
    DocumentContent,
    DocumentFile,
    DocumentSearchResult,
    EmailIndexingJob,
)
from app.external_api_clients.embedding_client import EmbeddingClient
from app.services.rag.ingestion.document.service import DocumentIngestionService
from app.services.rag.ingestion.email.service import EmailIngestionService
from app.services.rag.retrieval.document.service import DocumentRetrievalService
from app.services.rag.retrieval.email.ranking import merge_matches
from app.services.rag.retrieval.email.service import EmailRetrievalService
from app.workers.email_indexing import index_pending_emails


async def test_document_file_is_indexed_with_batch_embeddings(tmp_path: Path) -> None:
    path = tmp_path / "terms.md"
    path.write_text("# Delivery\n\nSigned approval is required.", encoding="utf-8")
    dao = AsyncMock(spec=DocumentChunkDAO)
    embedding = AsyncMock(spec=EmbeddingClient)
    embedding.get_embeddings.return_value = [[0.1, 0.2]]
    service = DocumentIngestionService(dao, embedding)
    assert await service.ingest_document(DocumentFile("terms", "Terms", path)) == 1
    doc_id, title, chunks = dao.replace_chunks.await_args.args
    assert doc_id == "terms" and title == "Terms"
    assert chunks[0].content == path.read_text(encoding="utf-8")
    assert chunks[0].index == 1 and chunks[0].embedding == [0.1, 0.2]
    embedding.get_embedding.assert_not_awaited()


@pytest.mark.parametrize("failure", ["empty", "embedding", "missing-vector"])
async def test_failed_document_preparation_keeps_existing_index(failure: str) -> None:
    dao = AsyncMock(spec=DocumentChunkDAO)
    embedding = AsyncMock(spec=EmbeddingClient)
    content = "" if failure == "empty" else "Document content."
    if failure == "embedding":
        embedding.get_embeddings.side_effect = ValueError("Embedding unavailable")
    else:
        embedding.get_embeddings.return_value = []
    service = DocumentIngestionService(dao, embedding)
    with pytest.raises(ValueError):
        await service.process_document(DocumentContent("terms", "Terms", content))
    dao.replace_chunks.assert_not_awaited()


async def test_document_retrieval_returns_sources_without_thread_dependencies() -> None:
    dao = AsyncMock(spec=DocumentChunkDAO)
    embedding = AsyncMock(spec=EmbeddingClient)
    embedding.get_embedding.return_value = [0.1, 0.2]
    dao.search.return_value = [
        DocumentSearchResult(uuid4(), "terms", "Delivery", 1, "Signed approval.", 0.9),
        DocumentSearchResult(uuid4(), "terms", "Delivery", 2, "Delivery date.", 0.8),
    ]
    service = DocumentRetrievalService(dao, embedding)
    result = await service.get_context("Delivery terms")
    assert result.used_document_ids == ["terms"]
    assert len(result.documents) == 2
    assert "Signed approval" in result.formatted_context
    dao.search.assert_awaited_once_with([0.1, 0.2], top_k=5)


async def test_disabled_document_search_skips_embedding_and_database() -> None:
    dao = AsyncMock(spec=DocumentChunkDAO)
    embedding = AsyncMock(spec=EmbeddingClient)
    service = DocumentRetrievalService(dao, embedding, top_k=0)
    assert not (await service.get_context("Delivery terms")).documents
    embedding.get_embedding.assert_not_awaited()
    dao.search.assert_not_awaited()
    with pytest.raises(ValueError):
        await service.get_context("Delivery terms", top_k_docs=-1)
    with pytest.raises(ValueError):
        await service.get_context(" ")


async def test_sender_only_search_does_not_request_semantic_embedding() -> None:
    emails = AsyncMock(spec=RawEmailDAO)
    chunks = AsyncMock(spec=EmailChunkDAO)
    embedding = AsyncMock(spec=EmbeddingClient)
    emails.search_emails.return_value = []
    owner_id = uuid4()
    criteria = MailSearchCriteria(sender="client@example.test")
    service = EmailRetrievalService(emails, chunks, embedding)
    assert await service.search(criteria, owner_id=owner_id) == []
    emails.search_emails.assert_awaited_once_with(criteria, owner_id=owner_id, limit=10)
    chunks.search.assert_not_awaited()
    embedding.get_embedding.assert_not_awaited()


def test_rrf_prefers_shared_candidates_and_deduplicates_each_ranking() -> None:
    now = datetime.now(UTC)
    a = MailSnippet("a", "thread", "A", "client", now, "A")
    b = MailSnippet("b", "thread", "B", "client", now, "B")
    c = MailSnippet("c", "thread", "C", "client", now, "C")
    matches = merge_matches([a, b, b], [c, b], 3)
    assert matches[0] == b
    assert {match.email_id for match in matches} == {"a", "b", "c"}


async def test_empty_email_clears_stale_chunks_without_embedding() -> None:
    dao = AsyncMock(spec=EmailChunkDAO)
    dao.replace_chunks.return_value = True
    embedding = AsyncMock(spec=EmbeddingClient)
    job = EmailIndexingJob(uuid4(), uuid4(), 1, datetime.now(UTC), "", "")
    assert await EmailIngestionService(dao, embedding).process_email(job)
    dao.replace_chunks.assert_awaited_once_with(job, [])
    embedding.get_embeddings.assert_not_awaited()


async def test_worker_applies_delay_and_continues_after_one_failed_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dao = AsyncMock(spec=EmailChunkDAO)
    service = AsyncMock(spec=EmailIngestionService)
    now = datetime.now(UTC)
    jobs = [
        EmailIndexingJob(uuid4(), uuid4(), 1, now, "Project", "Message")
        for _ in range(2)
    ]
    dao.pending_jobs.return_value = jobs
    service.process_email.side_effect = [ValueError("Invalid message"), True]
    sleep = AsyncMock(side_effect=asyncio.CancelledError)
    monkeypatch.setattr("app.workers.email_indexing.asyncio.sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await index_pending_emails(dao, service, RagWorkerConfig())
    cutoff = dao.pending_jobs.await_args.args[0]
    assert now - timedelta(minutes=30, seconds=2) <= cutoff
    assert cutoff <= datetime.now(UTC) - timedelta(minutes=30)
    assert service.process_email.await_count == 2
    sleep.assert_awaited_once_with(60)
