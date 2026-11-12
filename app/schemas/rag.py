from pydantic import BaseModel
from datetime import datetime


class RagChunk(BaseModel):
    id: str
    source_type: str  # "company_doc" | "thread_summary"
    source_id: str    # doc_id | thread_id
    thread_id: str | None = None
    date: datetime | None = None
    content: str
    score: float | None = None

