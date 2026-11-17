from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


@dataclass(frozen=True, slots=True)
class DocumentContent:
    doc_id: str
    title: str
    content: str


@dataclass(frozen=True, slots=True)
class DocumentFile:
    doc_id: str
    title: str
    file_path: Path


class RagChunk(BaseModel):
    id: str
    source_type: Literal["company_doc"] = "company_doc"
    source_id: str
    content: str
    score: float | None = None


class RAGContextResult(BaseModel):
    documents: list[RagChunk] = Field(default_factory=list)
    formatted_context: str = ""
    used_document_ids: list[str] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class IndexedChunk:
    index: int
    content: str
    embedding: list[float]


@dataclass(frozen=True, slots=True)
class DocumentSearchResult:
    id: UUID
    doc_id: str
    title: str
    chunk_index: int
    content: str
    score: float | None


@dataclass(frozen=True, slots=True)
class EmailIndexingJob:
    email_id: UUID
    account_id: UUID
    generation: int | None
    updated_at: datetime
    subject: str
    body: str = field(repr=False)
