from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.enums import GmailConnectionStatus


class GmailAccountData(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: UUID
    name: str
    gmail_email: str | None


class GmailConnectionData(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    gmail_account_id: UUID
    client_id: str | None
    client_secret_ciphertext: str | None = Field(repr=False)
    refresh_token_ciphertext: str | None = Field(repr=False)
    scopes: list[str]
    status: GmailConnectionStatus
    synced_through_at: datetime | None
    next_sync_at: datetime | None
    last_success_at: datetime | None
    lease_token: UUID | None = Field(repr=False)
    lease_expires_at: datetime | None
    generation: int
    pending_client_id: str | None
    pending_client_secret_ciphertext: str | None = Field(repr=False)
    oauth_state_digest: str | None = Field(repr=False)
    oauth_browser_digest: str | None = Field(repr=False)
    oauth_expires_at: datetime | None


@dataclass(frozen=True, slots=True)
class GmailAccountInfo:
    id: UUID
    name: str
    gmail_email: str | None
    status: GmailConnectionStatus
    last_success_at: datetime | None


@dataclass(frozen=True, slots=True)
class OAuthAttempt:
    state_digest: str
    browser_digest: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class ClaimedOAuthAttempt:
    account_id: UUID
    client_id: str
    secret_ciphertext: str = field(repr=False)
    browser_digest: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class AuthorizedMailbox:
    gmail_email: str
    scopes: list[str]
    refresh_token_ciphertext: str | None = field(repr=False)


@dataclass(frozen=True, slots=True)
class GmailOAuthStart:
    url: str
    browser_token: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class GmailSyncLease:
    account_id: UUID
    gmail_email: str = field(repr=False)
    client_id: str = field(repr=False)
    client_secret_ciphertext: str = field(repr=False)
    refresh_token_ciphertext: str = field(repr=False)
    synced_through_at: datetime | None
    token: UUID = field(repr=False)
    generation: int


@dataclass(frozen=True, slots=True)
class ImportedGmailMessage:
    gmail_message_id: str
    sender: str
    recipient: str
    date: datetime
    subject: str
    body: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class ImportedGmailThread:
    gmail_thread_id: str
    subject: str
    client_email: str
    messages: list[ImportedGmailMessage] = field(repr=False)
