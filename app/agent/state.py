from typing import TypedDict, Annotated
import operator

class AgentState(TypedDict):
    # Диалоговые сообщения (системные, пользовательские, ответы модели, результаты тулов)
    messages: Annotated[list[dict], operator.add]
    
    # Контекст безопасности
    run_id: str
    canary_token: str
    is_blocked: bool
    block_reason: str | None
    
    # Контекст работы агента
    current_thread_id: str | None
    rag_context: str
    used_document_ids: list[str]
    used_email_ids: list[str]
    
    # Результаты
    saved_draft_id: str | None
    final_response: str | None

