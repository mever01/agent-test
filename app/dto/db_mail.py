from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, field_validator, model_validator

from app.db.enums import AccountSource


@dataclass(frozen=True, slots=True, kw_only=True)
class ThreadWrite:
    """Данные цепочки с внутренним UUID и внешним ID почтового провайдера."""

    thread_id: UUID
    account_source: AccountSource
    account_id: UUID
    external_thread_id: str
    subject: str
    client_email: str


@dataclass(frozen=True, slots=True, kw_only=True)
class EmailWrite:
    """Данные письма, связанного с цепочкой того же аккаунта и источника."""

    email_id: UUID
    thread_id: UUID
    account_source: AccountSource
    account_id: UUID
    message_id: str
    sender: str
    recipient: str
    date: datetime
    subject: str
    body: str


@dataclass(frozen=True, slots=True, kw_only=True)
class DraftWrite:
    """Данные черновика с ключом для защиты от повторного создания."""

    thread_id: UUID
    recipient: str
    subject: str
    text_content: str
    operation_id: UUID | None = None


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
        if not any((
            self.words, self.sender, self.participant, self.start_date, self.end_date,
        )):
            raise ValueError("Укажите слова, отправителя, участника или период.")
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("Дата начала должна быть не позже даты окончания.")
        return self


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
    thread_last_date: datetime | None = None


@dataclass(frozen=True, slots=True)
class MailThreadDetails:
    thread_id: str
    subject: str
    client_email: str
    messages: list[MailMessage]
    mailbox_email: str | None = None


@dataclass(frozen=True, slots=True)
class MailDraft:
    id: str
    thread_id: str
    recipient: str
    subject: str
    text: str
    created_at: datetime | None
