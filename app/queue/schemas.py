from pydantic import BaseModel, Field
from datetime import datetime, timezone
import uuid


class BaseQueueEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:8]}")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class ThreadClosedEvent(BaseQueueEvent):
    event_type: str = "THREAD_CLOSED"
    thread_id: str

class DocIngestEvent(BaseQueueEvent):
    event_type: str = "DOC_INGEST"
    doc_id: str
    title: str
    file_path: str

