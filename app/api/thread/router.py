from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_current_user, get_thread_service, require_role
from app.db.models.user import User
from app.dto.db_mail import MailThreadDetails
from app.services.exceptions import ThreadNotFoundError
from app.services.db_mail.thread import ThreadService

router = APIRouter(prefix="/emails", tags=["Emails & Threads"])


@router.get(
    "/threads/{thread_id}",
    response_model=MailThreadDetails,
    dependencies=[Depends(require_role(["manager", "admin"]))],
)
async def get_thread_endpoint(
    thread_id: UUID,
    service: ThreadService = Depends(get_thread_service),
    user: User = Depends(get_current_user),
) -> MailThreadDetails:
    """Получение полной цепочки сообщений."""
    try:
        return await service.get_thread(thread_id, owner_id=user.id)
    except ThreadNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
