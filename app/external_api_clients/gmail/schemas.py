from __future__ import annotations

from pydantic import BaseModel, Field


class GmailMessageRef(BaseModel):
    id: str
    thread_id: str = Field(alias="threadId")


class GmailMessagePage(BaseModel):
    messages: list[GmailMessageRef] = Field(default_factory=list)
    next_page_token: str | None = Field(None, alias="nextPageToken")


class GmailHeader(BaseModel):
    name: str
    value: str


class GmailPartBody(BaseModel):
    data: str | None = None
    size: int = Field(0, ge=0)
    attachment_id: str | None = Field(None, alias="attachmentId")


class GmailPart(BaseModel):
    mime_type: str = Field(alias="mimeType")
    filename: str = ""
    headers: list[GmailHeader] = Field(default_factory=list)
    body: GmailPartBody | None = None
    parts: list[GmailPart] = Field(default_factory=list)


class GmailMessage(GmailMessageRef):
    label_ids: list[str] = Field(default_factory=list, alias="labelIds")
    internal_date_ms: int = Field(alias="internalDate", ge=0)
    payload: GmailPart | None = None


class GmailThread(BaseModel):
    id: str
    messages: list[GmailMessage] = Field(default_factory=list)


class GmailErrorReason(BaseModel):
    reason: str = ""


class GmailErrorMessage(BaseModel):
    errors: list[GmailErrorReason] = Field(default_factory=list)
    details: list[GmailErrorReason] = Field(default_factory=list)


class GmailErrorResponse(BaseModel):
    error: GmailErrorMessage


class GoogleTokenError(BaseModel):
    error: str
