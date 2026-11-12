from fastapi import APIRouter, Depends
from app.api.dependencies import get_mail_service, require_role
from app.db.schemas import MailDraft
from app.services.mail_service import MailService

router = APIRouter(prefix="/drafts", tags=["Drafts"])


@router.get(
    "/",
    response_model=list[MailDraft],
    dependencies=[Depends(require_role(["manager", "admin"]))],
)
async def list_drafts(mail_service: MailService = Depends(get_mail_service)) -> list[MailDraft]:
    """Просмотр созданных агентом черновиков."""
    return await mail_service.list_drafts()
