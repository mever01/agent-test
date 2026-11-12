from typing import Any
from langgraph.graph import StateGraph, END
from app.agent.state import AgentState
from app.agent.nodes import (
    agent_node,
    canary_guard_node,
    tools_node,
    rag_enrichment_node,
    block_node,
)
from app.external_api_clients.llm_client import LLMClient
from app.db.repositories.email_repository import EmailRepository
from app.rag.retrieval import RAGRetrievalService

def create_agent_graph(
    llm_client: LLMClient,
    email_repo: EmailRepository,
    rag_service: RAGRetrievalService,
):
    """
    Фабрика создания детерминированного графа агента на базе LangGraph.
    """
    workflow = StateGraph(AgentState)

    # 1. Асинхронные обертки для узлов графа
    async def _run_agent_node(state: AgentState) -> dict[str, Any]:
        return await agent_node(state, llm_client)

    async def _run_tools_node(state: AgentState) -> dict[str, Any]:
        return await tools_node(state, email_repo)

    async def _run_rag_node(state: AgentState) -> dict[str, Any]:
        return await rag_enrichment_node(state, rag_service)

    # 2. Регистрация узлов
    workflow.add_node("rag", _run_rag_node)
    workflow.add_node("agent", _run_agent_node)
    workflow.add_node("guard", canary_guard_node)
    workflow.add_node("tools", _run_tools_node)
    workflow.add_node("block", block_node)

    # 3. Стартовая точка: Сначала обогащаем запрос релевантным RAG-контекстом
    workflow.set_entry_point("rag")
    workflow.add_edge("rag", "agent")

    # 4. Маршрутизация после агента: ВСЕГДА в узел canary_guard
    workflow.add_edge("agent", "guard")

    # 5. Условная маршрутизация после проверки безопасности
    def route_after_guard(state: AgentState) -> str:
        if state.get("is_blocked"):
            return "block"

        last_message = state["messages"][-1]
        tool_calls = last_message.get("tool_calls", [])

        # Если модель решила вызвать инструмент:
        if tool_calls:
            return "tools"

        # Нет вызовов тулов -> агент дал финальный ответ
        return END

    workflow.add_conditional_edges(
        "guard",
        route_after_guard,
        {
            "block": "block",
            "tools": "tools",
            END: END,
        }
    )

    # После исполнения инструментов возвращаемся к рассуждению агента
    workflow.add_edge("tools", "agent")

    # После узла блокировки работа прекращается
    workflow.add_edge("block", END)

    return workflow.compile()

