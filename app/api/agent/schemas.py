from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    continuation_id: UUID | None = None


class ChatResponse(BaseModel):
    run_id: str
    response: str
    status: Literal["completed", "awaiting_input", "failed", "blocked"] = "completed"
    continuation_id: UUID | None = None
    draft_id: str | None = None
    used_document_ids: list[str] = Field(default_factory=list)
    used_email_ids: list[str] = Field(default_factory=list)
    is_blocked: bool = False
    block_reason: str | None = None
