import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from pydantic import ValidationError
import pytest

from app.broker.rag.schemas import ThreadClosedEvent, DocIngestEvent
from app.broker.rag.consumer import ThreadClosedConsumer, DocIngestConsumer


def test_thread_closed_event_validation():
    valid_uuid = uuid.uuid4()
    raw_json = f'{{"event_id": "00000000-0000-0000-0000-000000000001", "timestamp": "2026-01-01T00:00:00Z", "event_type": "THREAD_CLOSED", "thread_id": "{valid_uuid}"}}'

    event = ThreadClosedEvent.model_validate_json(raw_json)
    assert event.thread_id == valid_uuid
    assert isinstance(event.thread_id, uuid.UUID)

    # Невалидный UUID вызывает ValidationError
    invalid_json = '{"event_id": "00000000-0000-0000-0000-000000000002", "timestamp": "2026-01-01T00:00:00Z", "event_type": "THREAD_CLOSED", "thread_id": "not-a-uuid"}'
    with pytest.raises(ValidationError):
        ThreadClosedEvent.model_validate_json(invalid_json)


def test_doc_ingest_event_validation():
    raw_json = '{"event_id": "00000000-0000-0000-0000-000000000003", "timestamp": "2026-01-01T00:00:00Z", "event_type": "DOC_INGEST", "doc_id": "doc_1", "title": "Регламент", "file_path": "data/doc.md"}'

    event = DocIngestEvent.model_validate_json(raw_json)
    assert event.doc_id == "doc_1"
    assert event.title == "Регламент"
    assert isinstance(event.file_path, Path)
    assert event.file_path == Path("data/doc.md")

    # Отсутствие обязательного поля file_path
    invalid_json = '{"event_id": "00000000-0000-0000-0000-000000000004", "timestamp": "2026-01-01T00:00:00Z", "event_type": "DOC_INGEST", "doc_id": "doc_1"}'
    with pytest.raises(ValidationError):
        DocIngestEvent.model_validate_json(invalid_json)


async def test_thread_closed_consumer_handle():
    queue = MagicMock()
    service = MagicMock()
    service.ingest_thread = AsyncMock(return_value=True)

    consumer = ThreadClosedConsumer(queue=queue, ingestion_service=service)
    test_id = uuid.uuid4()
    event = ThreadClosedEvent(thread_id=test_id)

    await consumer.handle(event)
    service.ingest_thread.assert_awaited_once_with(thread_id=test_id)


async def test_doc_ingest_consumer_handle():
    queue = MagicMock()
    service = MagicMock()
    service.ingest_document = AsyncMock(return_value=3)

    consumer = DocIngestConsumer(queue=queue, ingestion_service=service)
    event = DocIngestEvent(
        doc_id="doc_test",
        title="Тест",
        file_path=Path("data/test.md"),
    )

    await consumer.handle(event)
    service.ingest_document.assert_awaited_once_with(
        doc_id="doc_test",
        title="Тест",
        file_path=Path("data/test.md"),
    )


async def test_consumer_on_message_validation_failure():
    queue = MagicMock()
    queue.name = "rag.threads.queue"
    service = MagicMock()
    consumer = ThreadClosedConsumer(queue=queue, ingestion_service=service)

    msg = MagicMock()
    msg.body = b'{"invalid": "data"}'
    msg.message_id = "msg_err"
    msg.reject = AsyncMock()
    msg.ack = AsyncMock()

    await consumer._on_message(msg)

    msg.reject.assert_awaited_once_with(requeue=False)
    msg.ack.assert_not_awaited()


async def test_consumer_on_message_success():
    queue = MagicMock()
    queue.name = "rag.threads.queue"
    service = MagicMock()
    service.ingest_thread = AsyncMock(return_value=True)
    consumer = ThreadClosedConsumer(queue=queue, ingestion_service=service)

    test_id = uuid.uuid4()
    event = ThreadClosedEvent(thread_id=test_id)

    msg = MagicMock()
    msg.body = event.model_dump_json().encode("utf-8")
    msg.message_id = "msg_ok"
    msg.reject = AsyncMock()
    msg.ack = AsyncMock()

    await consumer._on_message(msg)

    msg.ack.assert_awaited_once()
    msg.reject.assert_not_awaited()
