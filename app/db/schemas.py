from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, field_validator, model_validator


class MailSearchCriteria(BaseModel):
    words: str | None = None
    sender: str | None = None
    participant: str | None = None
    start_date: date | None = None
    end_date: date | None = None

    @field_validator("words", "sender", "participant")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return (value.strip() or None) if value is not None else None

    @model_validator(mode="after")
    def validate_filters(self) -> "MailSearchCriteria":
        if not any((self.words, self.sender, self.participant, self.start_date, self.end_date)):
            raise ValueError("Укажите слова, отправителя, участника или период.")
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("Дата начала должна быть не позже даты окончания.")
        return self



@dataclass(frozen=True, slots=True)
class IndexedDocumentChunk:
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
class ThreadSearchResult:
    id: UUID
    thread_id: UUID
    date: datetime | None
    content: str
    score: float | None

@dataclass(frozen=True, slots=True)
class MailMessage:
    id: str
    thread_id: str
    sender: str
    recipient: str
    date: datetime
    subject: str
    body: str


@dataclass(frozen=True, slots=True)
class MailSnippet:
    email_id: str
    thread_id: str
    subject: str
    sender: str
    date: datetime
    snippet: str


@dataclass(frozen=True, slots=True)
class MailThreadDetails:
    thread_id: str
    subject: str
    client_email: str
    status: str
    messages: list[MailMessage]

@dataclass(frozen=True, slots=True)
class MailDraft:
    id: str
    thread_id: str
    recipient: str
    subject: str
    text: str
    created_at: datetime | None