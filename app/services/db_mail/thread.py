from dataclasses import replace
from uuid import UUID

from app.db.dao.db_mail.thread import ThreadDAO
from app.dto.db_mail import MailSnippet, MailThreadDetails
from app.services.exceptions import ThreadNotFoundError


class ThreadService:
    def __init__(self, dao: ThreadDAO) -> None:
        self._dao = dao

    async def get_thread(
        self, thread_id: UUID, owner_id: UUID | None,
    ) -> MailThreadDetails:
        """Читает полную доступную цепочку или сообщает об её отсутствии."""
        thread = await self._dao.get_thread(thread_id, owner_id=owner_id)
        if thread is None:
            raise ThreadNotFoundError(f"Thread {thread_id} not found")
        return thread

    async def thread_activity(
        self, matches: list[MailSnippet], owner_id: UUID | None,
    ) -> list[MailSnippet]:
        """Дополняет результаты поиска датой последнего письма каждой цепочки."""
        dates = await self._dao.thread_activity(
            list(dict.fromkeys(UUID(item.thread_id) for item in matches)),
            owner_id=owner_id,
        )
        return [
            replace(item, thread_last_date=dates.get(UUID(item.thread_id)))
            for item in matches
        ]
