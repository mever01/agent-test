from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from pydantic import ValidationError

from app.api.dependencies import (
    get_current_user,
    get_email_retrieval_service,
    get_raw_email_service,
    require_role,
)
from app.db.models.user import User
from app.dto.db_mail import MailMessage, MailSearchCriteria, MailSnippet
from app.services.db_mail.raw_email import RawEmailService
from app.services.exceptions import EmailNotFoundError
from app.services.rag.retrieval.email.service import EmailRetrievalService

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
    service: EmailRetrievalService = Depends(get_email_retrieval_service),
    user: User = Depends(get_current_user),
) -> list[MailSnippet]:
    """Гибридный поиск писем в пределах владельца."""
    try:
        criteria = MailSearchCriteria(
            words=words, sender=sender, participant=participant,
            start_date=start_date, end_date=end_date,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=exc.errors(
                include_url=False, include_context=False, include_input=False,
            ),
        ) from exc
    return await service.search(criteria, owner_id=user.id)


@router.get(
    "/{email_id}",
    dependencies=[Depends(require_role(["manager", "admin"]))],
)
async def get_email_endpoint(
    email_id: UUID,
    service: RawEmailService = Depends(get_raw_email_service),
    user: User = Depends(get_current_user),
) -> MailMessage:
    """Возвращает полное письмо по его внутреннему ID."""
    try:
        return await service.get_email(email_id, owner_id=user.id)
    except EmailNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc),
        ) from exc
