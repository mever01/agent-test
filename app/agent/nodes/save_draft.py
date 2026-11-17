from dataclasses import replace
from uuid import UUID

from langgraph.runtime import Runtime
from sqlalchemy.exc import SQLAlchemyError

from app.agent.schemas import AgentResult
from app.agent.state import AgentContext, AgentState, AgentUpdate
from app.dto.db_mail import DraftWrite
from app.services.exceptions import ThreadNotFoundError


async def save_draft(
    state: AgentState,
    *,
    runtime: Runtime[AgentContext],
) -> AgentUpdate:
    draft = state["draft"]
    try:
        data = DraftWrite(
            thread_id=draft.thread_id,
            recipient=draft.recipient,
            subject=draft.subject,
            text_content=draft.text,
            operation_id=UUID(state["run_id"]),
        )
        draft_id = await runtime.context.drafts.create_draft(
            data, owner_id=runtime.context.owner_id,
        )
    except (SQLAlchemyError, OSError, ThreadNotFoundError):
        return {"result": AgentResult(
            state["run_id"], "Не удалось сохранить черновик.", status="failed"
        )}
    return {"result": replace(state["result"], draft_id=draft_id)}
