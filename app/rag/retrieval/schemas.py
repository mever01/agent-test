from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class RagChunk(BaseModel):
    id: str
    source_type: Literal["company_doc", "thread_summary"]
    source_id: str
    thread_id: str | None = None
    date: datetime | None = None
    content: str
    score: float | None = None


class RAGContextResult(BaseModel):
    documents: list[RagChunk] = Field(default_factory=list)
    threads: list[RagChunk] = Field(default_factory=list)

    formatted_context: str = ""

    used_document_ids: list[str] = Field(default_factory=list)
    used_thread_ids: list[str] = Field(default_factory=list)
