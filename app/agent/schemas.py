from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.schemas import MailSnippet


@dataclass(frozen=True, slots=True)
class AgentResult:
    run_id: str
    response: str
    status: Literal["completed", "awaiting_input", "failed", "blocked"] = "completed"
    continuation_id: UUID | None = None
    draft_id: str | None = None
    used_document_ids: list[str] = field(default_factory=list)
    used_email_ids: list[str] = field(default_factory=list)
    is_blocked: bool = False
    block_reason: str | None = None


class Classification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: Literal["search", "summary", "draft", "unclear", "send", "out_of_scope"] = Field(
        description=(
            "Конечная задача. Если просят и сводку, и черновик по одной цепочке, выбери draft."
        ),
    )


class SearchNeedsCriteria(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["needs_criteria"]


class SourcedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response: str = Field(min_length=1)
    email_ids: list[str] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)
    question: str | None = Field(default=None, min_length=1, max_length=500)


@dataclass(frozen=True, slots=True)
class Clarification:
    question: str
    kind: Literal["criteria", "candidate", "fact"]
    candidates: tuple[MailSnippet, ...] = ()
