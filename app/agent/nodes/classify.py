from langgraph.runtime import Runtime

from app.agent.nodes.security import checked_chat
from app.agent.prompts import CLASSIFY, RETRY
from app.agent.schemas import AgentResult, Classification
from app.agent.state import AgentContext, AgentState, AgentUpdate


async def classify(
    state: AgentState,
    *,
    runtime: Runtime[AgentContext],
) -> AgentUpdate:
    request = state["request"]
    classification: Classification | None = None
    for instruction in (CLASSIFY, f"{CLASSIFY}\n{RETRY}"):
        response = await checked_chat(
            runtime.context, state["run_id"],
            [
                {"role": "system", "content": instruction},
                {"role": "user", "content": request}
            ],
            stage="классификация запроса",
            output_schema=Classification,
        )
        try:
            if response.tool_calls:
                raise ValueError("Unexpected tool call")
            classification = Classification.model_validate_json(response.content or "")
            break
        except ValueError:
            continue
    if classification is None:
        return {
            "result": AgentResult(
                state["run_id"],
                "Не удалось определить задачу. Попробуйте ещё раз.",
                status="failed",
            ),
            "next_step": "__end__",
        }

    task = classification.task
    if task in ("unclear", "out_of_scope", "send"):
        messages = {
            "unclear": "Переформулируйте запрос и укажите, что нужно сделать с перепиской.",
            "out_of_scope": (
                "Я могу найти письма, изложить договорённости или подготовить черновик."
            ),
            "send": "Я могу подготовить и сохранить черновик ответа.",
        }
        return {
            "result": AgentResult(state["run_id"],
            messages[task]),
            "next_step": "__end__"
        }
    return {"intent": task, "next_step": "search"}
