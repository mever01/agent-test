from uuid import UUID

from app.db.dao.db_mail.raw_email import RawEmailDAO
from app.dto.db_mail import MailCursor, MailFilters, MailMessage, MailPage
from app.services.exceptions import EmailNotFoundError


class RawEmailService:
    def __init__(self, dao: RawEmailDAO) -> None:
        self._dao = dao

    async def list_page(
        self,
        filters: MailFilters,
        *,
        owner_id: UUID,
        account_id: UUID | None,
        cursor: MailCursor | None,
        limit: int,
    ) -> MailPage:
        return await self._dao.list_page(
            filters,
            owner_id=owner_id,
            account_id=account_id,
            cursor=cursor,
            limit=limit,
        )

    async def get_email(self, email_id: UUID, *, owner_id: UUID) -> MailMessage:
        """Возвращает содержимое письма для просмотра."""
        email = await self._dao.get_email(email_id, owner_id=owner_id)
        if email is None:
            raise EmailNotFoundError(f"Email {email_id} not found")
        return email
