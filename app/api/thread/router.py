from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_mail_service, require_role
from app.db.schemas import MailThreadDetails
from app.services.exceptions import ThreadNotFoundError
from app.services.mail_service import MailService, ThreadClosed

router = APIRouter(prefix="/emails", tags=["Emails & Threads"])


@router.get(
    "/threads/{thread_id}",
    response_model=MailThreadDetails,
    dependencies=[Depends(require_role(["manager", "admin"]))],
)
async def get_thread_endpoint(
    thread_id: UUID,
    mail_service: MailService = Depends(get_mail_service),
) -> MailThreadDetails:
    """Получение полной цепочки сообщений."""
    try:
        return await mail_service.get_thread(thread_id)
    except ThreadNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.post(
    "/threads/{thread_id}/close",
    dependencies=[Depends(require_role(["manager", "admin"]))],
)
async def close_thread_endpoint(
    thread_id: UUID,
    mail_service: MailService = Depends(get_mail_service),
) -> ThreadClosed:
    """Закрытие треда:

    1. Перевод статуса в 'closed' в БД.
    2. Публикация события THREAD_CLOSED для фонового сжатия и векторизации.
    """
    try:
        return await mail_service.close_thread(thread_id)
    except ThreadNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
