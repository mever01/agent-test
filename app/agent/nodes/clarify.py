from uuid import UUID

from langgraph.types import interrupt

from app.agent.schemas import AgentResult
from app.agent.state import AgentState, AgentUpdate


def clarify(state: AgentState) -> AgentUpdate:
    question = state["clarification"]
    assert question is not None
    answer = interrupt(question.question).strip()
    if answer.casefold() in {"отмена", "отмени", "отменить"}:
        return {"result": AgentResult(state["run_id"], "Обращение отменено."),
                "clarification": None, "next_step": "__end__"}
    if not answer:
        return {"next_step": "clarify"}
    if question.kind == "candidate":
        for index, candidate in enumerate(question.candidates, 1):
            if answer in (str(index), candidate.thread_id):
                return {"thread_id": UUID(candidate.thread_id), "clarification": None,
                        "next_step": "read_and_retrieve"}
        if answer.isdecimal() or answer.casefold() in {"не помню", "не знаю"}:
            return {"next_step": "clarify"}
    if question.kind in {"criteria", "candidate"}:
        previous = state.get("clarification_answer")
        return {"thread_id": None, "thread": None, "rag_chunks": [], "clarification": None,
                "clarification_answer": f"{previous}\n{answer}" if previous else answer,
                "next_step": "search"}
    return {"clarification_answer": answer, "clarification": None, "next_step": "prepare_result"}
