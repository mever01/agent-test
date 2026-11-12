
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class QueueEventType(StrEnum):
    THREAD_CLOSED = "THREAD_CLOSED"
    DOC_INGEST = "DOC_INGEST"


class BaseQueueEvent(BaseModel):
    # TODO: При повторной публикации одного и того же события сохранять event_id,
    # чтобы обеспечить идемпотентность consumer и избежать повторной обработки.
    event_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC)
    )


class ThreadClosedEvent(BaseQueueEvent):
    event_type: Literal[QueueEventType.THREAD_CLOSED] = (
        QueueEventType.THREAD_CLOSED
    )
    thread_id: UUID


class DocIngestEvent(BaseQueueEvent):
    event_type: Literal[QueueEventType.DOC_INGEST] = (
        QueueEventType.DOC_INGEST
    )
    doc_id: str
    title: str
    file_path: Path
