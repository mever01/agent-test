from pydantic import BaseModel, Field
from datetime import datetime

class EmailMessage(BaseModel):
    id: str
    thread_id: str
    sender: str
    recipient: str
    date: datetime
    subject: str
    body: str

class EmailSnippet(BaseModel):
    email_id: str
    thread_id: str
    subject: str
    sender: str
    date: datetime
    snippet: str

class ThreadDetails(BaseModel):
    thread_id: str
    subject: str
    client_email: str
    status: str
    messages: list[EmailMessage]

class DraftCreate(BaseModel):
    thread_id: str
    recipient: str
    subject: str
    text: str

class DraftResponse(BaseModel):
    draft_id: str
    thread_id: str
    status: str = "saved"

