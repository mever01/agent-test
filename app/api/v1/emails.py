import uuid
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.api.dependencies import get_email_repo, get_event_publisher, require_role
from app.db.repositories.email_repository import EmailRepository
from app.queue.publisher import EventPublisher
from app.schemas.email import EmailSnippet, ThreadDetails

router = APIRouter(prefix="/emails", tags=["Emails & Threads"])

@router.get(
    "/search",
    response_model=list[EmailSnippet],
    dependencies=[Depends(require_role(["manager", "admin"]))],
)
async def search_emails_endpoint(
    words: str = Query(..., description="Ключевые слова или артикулы"),
    sender: str | None = Query(None, description="Отправитель"),
    start_date: date | None = Query(None, description="Начало периода (YYYY-MM-DD)"),
    end_date: date | None = Query(None, description="Конец периода (YYYY-MM-DD)"),
    email_repo: EmailRepository = Depends(get_email_repo),
):
    """Полнотекстовый и триграммный поиск по письмам."""
    return await email_repo.search_emails(
        words=words, sender=sender, start_date=start_date, end_date=end_date
    )

@router.get(
    "/threads/{thread_id}",
    response_model=ThreadDetails,
    dependencies=[Depends(require_role(["manager", "admin"]))],
)
async def get_thread_endpoint(
    thread_id: uuid.UUID,
    email_repo: EmailRepository = Depends(get_email_repo),
):
    """Получение полной цепочки сообщений."""
    thread = await email_repo.get_thread(thread_id)
    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Цепочка с ID '{thread_id}' не найдена.",
        )
    return thread

@router.post(
    "/threads/{thread_id}/close",
    dependencies=[Depends(require_role(["manager", "admin"]))],
)
async def close_thread_endpoint(
    thread_id: uuid.UUID,
    email_repo: EmailRepository = Depends(get_email_repo),
    publisher: EventPublisher = Depends(get_event_publisher),
):
    """
    Закрытие треда:
    1. Перевод статуса в 'closed' в БД.
    2. Публикация события THREAD_CLOSED в RabbitMQ (rag.threads.queue) для фонового сжатия и векторизации.
    """
    success = await email_repo.close_thread(thread_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Цепочка '{thread_id}' не найдена.",
        )

    # Публикация в очередь
    try:
        await publisher.publish_thread_closed(str(thread_id))
    except Exception:
        # Логируем, но не блокируем ответ API
        pass

    return {"status": "closed", "thread_id": str(thread_id), "queued_for_rag": True}

