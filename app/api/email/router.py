from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, status

from pydantic import ValidationError

from app.api.dependencies import get_mail_service, require_role
from app.db.schemas import MailSearchCriteria, MailSnippet
from app.services.mail_service import MailService

router = APIRouter(prefix="/emails", tags=["Emails & Threads"])


@router.get(
    "/search",
    response_model=list[MailSnippet],
    dependencies=[Depends(require_role(["manager", "admin"]))],
)
async def search_emails_endpoint(
    words: str | None = Query(None, description="Ключевые слова или артикулы"),
    sender: str | None = Query(None, description="Отправитель"),
    participant: str | None = Query(None, description="Email участника переписки"),
    start_date: date | None = Query(None, description="Начало периода (YYYY-MM-DD)"),
    end_date: date | None = Query(None, description="Конец периода (YYYY-MM-DD)"),
    mail_service: MailService = Depends(get_mail_service),
) -> list[MailSnippet]:
    """Полнотекстовый и триграммный поиск по письмам."""
    try:
        criteria = MailSearchCriteria(
            words=words, sender=sender, participant=participant,
            start_date=start_date, end_date=end_date,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=exc.errors(include_url=False, include_context=False, include_input=False),
        ) from exc
    return await mail_service.search_emails(**criteria.model_dump())
