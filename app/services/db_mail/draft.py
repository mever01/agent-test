from uuid import UUID

from app.db.dao.db_mail.draft import DraftDAO
from app.dto.db_mail import DraftWrite, MailDraft
from app.services.exceptions import ThreadNotFoundError


class DraftService:
    def __init__(self, dao: DraftDAO) -> None:
        self._dao = dao

    async def create_draft(self, data: DraftWrite, owner_id: UUID | None) -> str:
        """Сохраняет черновик доступной цепочки с защитой от повторной операции."""
        draft_id = await self._dao.save_draft(data, owner_id=owner_id)
        if draft_id is None:
            raise ThreadNotFoundError(f"Thread {data.thread_id} not found")
        return draft_id

    async def draft_for_operation(
        self, operation_id: UUID, owner_id: UUID | None,
    ) -> str | None:
        """Возвращает ранее созданный черновик операции в пределах владельца."""
        return await self._dao.draft_for_operation(operation_id, owner_id=owner_id)

    async def list_drafts(
        self, limit: int, owner_id: UUID | None,
    ) -> list[MailDraft]:
        """Возвращает последние доступные владельцу черновики."""
        return await self._dao.list_drafts(limit=limit, owner_id=owner_id)
