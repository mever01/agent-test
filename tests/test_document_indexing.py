import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from app.broker.rag.consumer import DocIngestConsumer
from app.broker.rag.schemas import DocIngestEvent
from app.dto.rag import DocumentFile
from app.workers import document_indexing, email_indexing


def make_event() -> DocIngestEvent:
    return DocIngestEvent(
        doc_id="delivery", title="Terms", file_path=Path("data/doc.md"),
    )


def test_document_event_validation() -> None:
    event = DocIngestEvent.model_validate_json(make_event().model_dump_json())
    assert event.file_path == Path("data/doc.md")
    with pytest.raises(ValidationError):
        DocIngestEvent.model_validate({"doc_id": "missing-file"})


async def test_document_consumer_passes_domain_dto() -> None:
    service = MagicMock()
    service.ingest_document = AsyncMock(return_value=3)
    consumer = DocIngestConsumer(queue=MagicMock(), ingestion_service=service)
    event = make_event()
    await consumer.handle(event)
    service.ingest_document.assert_awaited_once_with(DocumentFile(
        event.doc_id, event.title, event.file_path,
    ))


@pytest.mark.parametrize("outcome", ["success", "invalid", "failure"])
async def test_document_acknowledgment_follows_processing(outcome: str) -> None:
    service = MagicMock()
    service.ingest_document = AsyncMock(return_value=2)
    if outcome == "failure":
        service.ingest_document.side_effect = RuntimeError("Index unavailable")
    consumer = DocIngestConsumer(queue=MagicMock(), ingestion_service=service)
    message = MagicMock()
    message.body = (
        b"{}" if outcome == "invalid" else make_event().model_dump_json().encode()
    )
    message.reject = AsyncMock()
    message.ack = AsyncMock()
    await consumer._on_message(message)
    if outcome == "success":
        message.ack.assert_awaited_once()
        message.reject.assert_not_awaited()
    else:
        message.reject.assert_awaited_once_with(requeue=False)
        message.ack.assert_not_awaited()


async def test_document_worker_closes_resources_on_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    embedding = MagicMock(close=AsyncMock())
    dispose = AsyncMock()
    consumer = MagicMock(start=AsyncMock(side_effect=asyncio.CancelledError))
    rabbit = MagicMock()
    rabbit.__aenter__ = AsyncMock(return_value=rabbit)
    rabbit.__aexit__ = AsyncMock(return_value=False)
    channel = MagicMock(set_qos=AsyncMock())
    rabbit.get_channel = AsyncMock(return_value=channel)
    topology = MagicMock(setup=AsyncMock(return_value=MagicMock()))
    monkeypatch.setattr(document_indexing, "engine", MagicMock(dispose=dispose))
    monkeypatch.setattr(document_indexing, "EmbeddingClient", lambda: embedding)
    monkeypatch.setattr(document_indexing, "RabbitMQClient", lambda url: rabbit)
    monkeypatch.setattr(document_indexing, "RAGTopology", lambda channel: topology)
    monkeypatch.setattr(
        document_indexing, "DocIngestConsumer", lambda **kwargs: consumer,
    )

    with pytest.raises(asyncio.CancelledError):
        await document_indexing.main()
    consumer.start.assert_awaited_once()
    embedding.close.assert_awaited_once()
    dispose.assert_awaited_once()
    rabbit.__aexit__.assert_awaited_once()


async def test_email_worker_starts_its_own_loop_and_closes_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    embedding = MagicMock(close=AsyncMock())
    dispose = AsyncMock()
    email_dao, service = MagicMock(), MagicMock()
    indexing = AsyncMock(side_effect=asyncio.CancelledError)
    monkeypatch.setattr(email_indexing, "engine", MagicMock(dispose=dispose))
    monkeypatch.setattr(email_indexing, "EmbeddingClient", lambda: embedding)
    monkeypatch.setattr(email_indexing, "EmailChunkDAO", lambda sessions: email_dao)
    monkeypatch.setattr(email_indexing, "EmailIngestionService", lambda *args: service)
    monkeypatch.setattr(email_indexing, "index_pending_emails", indexing)

    with pytest.raises(asyncio.CancelledError):
        await email_indexing.main()
    indexing.assert_awaited_once_with(
        email_dao, service, email_indexing.settings.rag_worker,
    )
    embedding.close.assert_awaited_once()
    dispose.assert_awaited_once()
