import json
import logging
from typing import Any
from app.agent.state import AgentState
from app.agent.tools.schemas import TOOLS_DEFINITIONS
from app.agent.tools.handlers import execute_tool_call
from app.external_api_clients.llm_client import LLMClient
from app.db.repositories.email_repository import EmailRepository
from app.rag.retrieval import RAGRetrievalService
from app.guardrails.security_logger import log_canary_leak
from app.guardrails.tools_guard import check_tool_calls_for_canary
from app.guardrails.outbound.canary_detector import is_canary_leaked

logger = logging.getLogger(__name__)

async def agent_node(state: AgentState, llm_client: LLMClient) -> dict[str, Any]:
    """Шаг мышления LLM: выбирает инструмент или формирует ответ пользователю."""
    response = await llm_client.chat(
        messages=state["messages"],
        tools=TOOLS_DEFINITIONS,
        tool_choice="auto",
    )

    assistant_message: dict[str, Any] = {
        "role": "assistant",
        "content": response.content or "",
    }
    if response.tool_calls:
        assistant_message["tool_calls"] = response.tool_calls
        logger.info(f"[AGENT] Запрос на вызов инструментов: {[tc.get('name') for tc in response.tool_calls]}")
    else:
        logger.info(f"[AGENT] Финальный ответ сформулирован (длина: {len(response.content or '')})")

    return {
        "messages": [assistant_message],
        "final_response": response.content,
    }

def canary_guard_node(state: AgentState) -> dict[str, Any]:
    """
    Детерминированный перехват утечек Canary Token.
    Проверяет аргументы инструментов и ответ модели.
    """
    last_message = state["messages"][-1]
    canary = state["canary_token"]
    run_id = state["run_id"]

    # 1. Проверяем аргументы вызовов инструментов
    tool_calls = last_message.get("tool_calls", [])
    if tool_calls and check_tool_calls_for_canary(tool_calls, canary):
        logger.critical(f"[SECURITY ALERT] Обнаружена утечка Canary Token в аргументах вызова инструмента! run_id={run_id}")
        log_canary_leak(run_id=run_id, location="tool_call_arguments")
        return {"is_blocked": True, "block_reason": "CANARY_MATCH"}

    # 2. Проверяем тело ответа модели
    content = last_message.get("content", "")
    if content and is_canary_leaked(content, canary):
        logger.critical(f"[SECURITY ALERT] Обнаружена утечка Canary Token в тексте ответа модели! run_id={run_id}")
        log_canary_leak(run_id=run_id, location="model_response")
        return {"is_blocked": True, "block_reason": "CANARY_MATCH"}

    return {"is_blocked": False}

async def tools_node(state: AgentState, email_repo: EmailRepository) -> dict[str, Any]:
    """Исполнение вызовов инструментов по оперативной базе писем."""
    last_message = state["messages"][-1]
    tool_calls = last_message.get("tool_calls", [])

    tool_messages = []
    saved_draft_id = state.get("saved_draft_id")
    current_thread_id = state.get("current_thread_id")
    used_email_ids = list(state.get("used_email_ids", []))

    for tc in tool_calls:
        name = tc.get("name") or tc.get("function", {}).get("name", "")
        args = tc.get("args")
        if args is None and "function" in tc:
            args = tc["function"].get("arguments", {})
        logger.info(f"[TOOLS] Выполнение инструмента '{name}' с аргументами: {args}")
        result_str = await execute_tool_call(name, args, email_repo)
        logger.info(f"[TOOLS] Результат инструмента '{name}': {result_str[:150]}...")

        # Анализируем результат
        if name == "create_draft":
            try:
                res_data = json.loads(result_str)
                saved_draft_id = res_data.get("draft_id")
            except Exception:
                pass
        elif name == "read_thread":
            if isinstance(args, dict) and "thread_id" in args:
                current_thread_id = args["thread_id"]
        elif name == "search_emails":
            # Вытягиваем email_id из результата
            pass

        tool_messages.append({
            "role": "tool",
            "tool_call_id": tc.get("id", "call_default"),
            "name": name,
            "content": result_str,
        })

    return {
        "messages": tool_messages,
        "saved_draft_id": saved_draft_id,
        "current_thread_id": current_thread_id,
        "used_email_ids": used_email_ids,
    }

async def rag_enrichment_node(state: AgentState, rag_service: RAGRetrievalService) -> dict[str, Any]:
    """
    Внутренний этап RAG: выполняется перед генерацией сводки или черновика.
    Подтягивает релевантные регламенты компании и архив прошлых тредов.
    """
    user_message = ""
    for m in state.get("messages", []):
        if m.get("role") == "user":
            user_message = m.get("content", "")
            break

    logger.info(f"[RAG] Поиск контекста в базе знаний по запросу: '{user_message[:100]}'")
    rag_result = await rag_service.get_context(query=user_message)
    logger.info(f"[RAG] Найдено документов: {len(rag_result.documents)}, прошлых тредов: {len(rag_result.threads)}")

    used_docs = list(set(state.get("used_document_ids", []) + rag_result.used_document_ids))
    used_threads = list(set(state.get("used_email_ids", []) + rag_result.used_thread_ids))

    system_rag_message = {
        "role": "system",
        "content": (
            "--- ВНУТРЕННИЙ RAG-КОНТЕКСТ (Справочники и история договоренностей) ---\n"
            f"{rag_result.formatted_context}\n"
            "Инструкция: используй эти сведения при ответе клиенту и подготовке черновика. "
            "В ответе обязательно укажи использованные ID документов и писем."
        )
    }

    return {
        "messages": [system_rag_message],
        "rag_context": rag_result.formatted_context,
        "used_document_ids": used_docs,
        "used_email_ids": used_threads,
    }

def block_node(state: AgentState) -> dict[str, Any]:
    """Узел безопасной блокировки: возвращает нейтральный ответ и прекращает работу."""
    neutral_message = "Запрос заблокирован политикой безопасности."
    return {
        "is_blocked": True,
        "final_response": neutral_message,
        "messages": [{"role": "assistant", "content": neutral_message}],
    }

