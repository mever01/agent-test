from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import TypedDict

from app.agent.schemas import AgentResult, Clarification
from app.agent.tools import CreateDraftArgs
from app.db.schemas import MailThreadDetails
from app.external_api_clients.llm_client import LLMClient
from app.rag.retrieval.schemas import RagChunk
from app.rag.retrieval.service import RAGRetrievalService
from app.services.mail_service import MailService

Step = Literal[
    "search", "read_and_retrieve",
    "prepare_result", "clarify",
    "save_draft", "__end__"
]


class AgentUpdate(TypedDict, total=False):
    intent: Literal["search", "summary", "draft"]
    thread_id: UUID | None
    thread: MailThreadDetails | None
    rag_chunks: list[RagChunk]
    clarification: Clarification | None
    clarification_answer: str
    draft: CreateDraftArgs
    result: AgentResult
    next_step: Step


class AgentState(AgentUpdate):
    run_id: str
    owner_id: UUID | None
    request: str


class AgentContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    llm: LLMClient
    mail: MailService
    rag: RAGRetrievalService
    canary: str = Field(repr=False)
