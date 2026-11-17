from fastapi import APIRouter, Depends
from app.api.dependencies import get_current_user, get_draft_service, require_role
from app.db.models.user import User
from app.dto.db_mail import MailDraft
from app.services.db_mail.draft import DraftService

router = APIRouter(prefix="/drafts", tags=["Drafts"])


@router.get(
    "/",
    response_model=list[MailDraft],
    dependencies=[Depends(require_role(["manager", "admin"]))],
)
async def list_drafts(
    service: DraftService = Depends(get_draft_service),
    user: User = Depends(get_current_user),
) -> list[MailDraft]:
    """Просмотр созданных агентом черновиков."""
    return await service.list_drafts(limit=10, owner_id=user.id)
