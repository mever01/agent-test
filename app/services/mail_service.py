import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from core.utils.mixins.logger import LoggerMixin
from app.db.repositories.mail_repository import MailRepository
from app.broker.rag.producer import RAGProducer
from app.db.schemas import MailDraft, MailSnippet, MailThreadDetails
from app.services.exceptions import ThreadNotFoundError


@dataclass(frozen=True, slots=True)
class ThreadClosed:
    status: Literal["closed"]
    thread_id: str
    queued_for_rag: bool


class MailService(LoggerMixin):
    def __init__(
        self,
        mail_repo: MailRepository,
        rag_producer: RAGProducer,
    ) -> None:
        self._mail_repo = mail_repo
        self._rag_producer = rag_producer

    async def get_thread(
        self,
        thread_id: uuid.UUID,
    ) -> MailThreadDetails:
        """Получает детали треда или выбрасывает ThreadNotFoundError."""
        thread = await self._mail_repo.get_thread(thread_id)
        if thread is None:
            raise ThreadNotFoundError(f"Thread {thread_id} not found")
        return thread

    async def close_thread(
        self,
        thread_id: uuid.UUID,
    ) -> ThreadClosed:
        """Закрывает тред и отправляет событие в брокер сообщений."""
        updated = await self._mail_repo.close_thread(thread_id)
        if not updated:
            raise ThreadNotFoundError(f"Thread {thread_id} not found")

        queued_for_rag = False
        try:
            await self._rag_producer.publish_thread_closed(thread_id)
            queued_for_rag = True
        except Exception:
            self.logger.warning(
                "Failed to publish thread_closed event: thread_id=%s",
                thread_id,
                exc_info=True,
                )

        return ThreadClosed("closed", str(thread_id), queued_for_rag)

    async def search_emails(
        self,
        words: str | None = None,
        sender: str | None = None,
        start_date: date | datetime | None = None,
        end_date: date | datetime | None = None,
        limit: int = 10,
        *,
        participant: str | None = None,
    ) -> list[MailSnippet]:
        """Поиск по письмам."""
        return await self._mail_repo.search_emails(
            words=words,
            sender=sender,
            start_date=start_date,
            end_date=end_date,
            participant=participant,
            limit=limit,
        )

    async def draft_for_operation(self, operation_id: uuid.UUID) -> str | None:
        return await self._mail_repo.draft_for_operation(operation_id)

    async def create_draft(
        self,
        thread_id: uuid.UUID | str,
        recipient: str,
        subject: str,
        text_content: str,
        operation_id: uuid.UUID | None = None,
    ) -> str:
        """Создает черновик письма."""
        tid = (
            thread_id
            if isinstance(thread_id, uuid.UUID)
            else uuid.UUID(str(thread_id))
        )
        return await self._mail_repo.save_draft(
            thread_id=tid,
            recipient=recipient,
            subject=subject,
            text_content=text_content,
            **({"operation_id": operation_id} if operation_id is not None else {}),
        )

    async def list_drafts(
        self,
        limit: int = 10,
    ) -> list[MailDraft]:
        """Возвращает список черновиков."""
        return await self._mail_repo.list_drafts(limit=limit)
