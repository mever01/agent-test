import uuid
import logging
import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from app.schemas.chat import ChatRequest, ChatResponse
from app.api.dependencies import (
    get_email_repo,
    get_rag_retrieval_service,
    get_llm_client,
    require_role,
)
from app.db.repositories.email_repository import EmailRepository
from app.rag.retrieval import RAGRetrievalService
from app.external_api_clients.llm_client import LLMClient
from app.agent.graph import create_agent_graph
from app.agent.prompts import generate_canary_token, build_system_prompt
from app.guardrails.inbound.injection_detector import detect_prompt_injection
from app.guardrails.inbound.pii_masker import mask_pii
from app.guardrails.outbound.canary_detector import is_canary_leaked
from app.guardrails.security_logger import log_canary_leak

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["Agent"])

@router.post(
    "/chat",
    response_model=ChatResponse,
    dependencies=[Depends(require_role(["manager", "admin"]))],
)
async def chat_with_agent(
    payload: ChatRequest,
    email_repo: EmailRepository = Depends(get_email_repo),
    rag_service: RAGRetrievalService = Depends(get_rag_retrieval_service),
    llm_client: LLMClient = Depends(get_llm_client),
):
    """
    Основная ручка взаимодействия с агентом:
    1. Inbound Guardrails (проверка на инъекции, маскирование PII).
    2. Генерация уникального Canary Token и сборка системного промпта.
    3. Запуск LangGraph с детерминированным контролем безопасности и RAG.
    4. Outbound Guardrails (дополнительная гарантия невыхода токена).
    """
    run_id = f"run_{uuid.uuid4().hex[:8]}"

    # 1. Inbound Guardrails
    has_injection, inject_reason = detect_prompt_injection(payload.message)
    if has_injection:
        logger.warning(f"Inbound Guardrails заблокировал запрос: {inject_reason} (run_id={run_id})")
        return ChatResponse(
            run_id=run_id,
            response="Запрос заблокирован политикой безопасности (обнаружена попытка prompt injection).",
            is_blocked=True,
            block_reason=inject_reason,
        )

    sanitized_prompt = mask_pii(payload.message)

    # 2. Canary Token и Промпт
    canary_token = generate_canary_token()
    system_prompt = build_system_prompt(canary_token)

    # 3. Инициализация LangGraph агента
    agent_graph = create_agent_graph(
        llm_client=llm_client,
        email_repo=email_repo,
        rag_service=rag_service,
    )

    initial_state = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": sanitized_prompt},
        ],
        "run_id": run_id,
        "canary_token": canary_token,
        "is_blocked": False,
        "block_reason": None,
        "current_thread_id": None,
        "rag_context": "",
        "used_document_ids": [],
        "used_email_ids": [],
        "saved_draft_id": None,
        "final_response": None,
    }

    try:
        final_state = await agent_graph.ainvoke(initial_state)
    except httpx.ReadTimeout:
        logger.error("Превышено время ожидания ответа от LLM (httpx.ReadTimeout)")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Превышено время ожидания ответа от языковой модели (LLM Timeout). Попробуйте повторить запрос или увеличить LLM_TIMEOUT.",
        )
    except Exception as e:
        logger.error(f"Ошибка при исполнении графа агента: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка при обработке запроса агентом.",
        )

    # 4. Outbound Guardrails: Финальная проверка перед отдачей клиенту
    resp_text = final_state.get("final_response") or "Ответ сформирован."
    if is_canary_leaked(resp_text, canary_token) or final_state.get("is_blocked"):
        if not final_state.get("is_blocked"):
            log_canary_leak(run_id=run_id, location="model_response")
        return ChatResponse(
            run_id=run_id,
            response="Запрос заблокирован политикой безопасности.",
            is_blocked=True,
            block_reason="CANARY_MATCH",
        )

    return ChatResponse(
        run_id=run_id,
        response=resp_text,
        draft_id=final_state.get("saved_draft_id"),
        used_document_ids=final_state.get("used_document_ids", []),
        used_email_ids=final_state.get("used_email_ids", []),
        is_blocked=False,
    )

