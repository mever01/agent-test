import json

import httpx
from langgraph.runtime import Runtime
from sqlalchemy.exc import SQLAlchemyError

from app.agent.nodes.security import checked_chat
from app.agent.prompts import READ, RETRY
from app.agent.schemas import AgentResult
from app.agent.state import AgentContext, AgentState, AgentUpdate
from app.agent.tools import READ_THREAD, ReadThreadArgs, tool_arguments
from app.services.exceptions import ThreadNotFoundError


async def read_and_retrieve(
    state: AgentState,
    *,
    runtime: Runtime[AgentContext],
) -> AgentUpdate:
    run_id = state["run_id"]
    thread_id = state["thread_id"]
    request = json.dumps({"request": state["request"], "thread_id": str(thread_id)})
    read_call: ReadThreadArgs | None = None
    for instruction in (READ, f"{READ}\n{RETRY}"):
        response = await checked_chat(
            runtime.context,
            run_id,
            [
                {"role": "system", "content": instruction},
                {"role": "user", "content": request},
            ],
            tools=[READ_THREAD],
            stage="выбор цепочки для чтения",
        )
        try:
            call = tool_arguments(response, "read_thread", ReadThreadArgs)
            if call.thread_id != thread_id:
                raise ValueError("Unexpected thread")
            read_call = call
            break
        except ValueError:
            continue
    if read_call is None:
        return {"result": AgentResult(run_id, "Не удалось выбрать цепочку.", status="failed"),
                "next_step": "__end__"}

    try:
        thread = await runtime.context.mail.get_thread(read_call.thread_id)
        if not thread.messages:
            return {
                "result": AgentResult(run_id, "В выбранной цепочке нет писем."),
                "next_step": "__end__",
            }
        thread_text = "\n".join(
            f"{mail.subject}\n{mail.body}" for mail in reversed(thread.messages)
        )
        rag_query = f"{state['request']}\n{thread_text[:12000]}"
        rag = await runtime.context.rag.get_context(query=rag_query)
    except ThreadNotFoundError:
        return {
            "result": AgentResult(run_id, "Выбранная цепочка больше недоступна.", status="failed"),
            "next_step": "__end__",
        }
    except (SQLAlchemyError, httpx.HTTPError, OSError, ValueError):
        return {
            "result": AgentResult(
                run_id, "Не удалось загрузить цепочку или RAG-контекст.", status="failed",
            ),
            "next_step": "__end__",
        }
    return {
        "thread": thread,
        "rag_chunks": [*rag.documents, *rag.threads],
        "next_step": "prepare_result",
    }
