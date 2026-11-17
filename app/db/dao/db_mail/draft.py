from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.dao.query_helpers import accessible_account, lock_accessible_account
from app.db.models import Draft, Thread
from app.dto.db_mail import DraftWrite, MailDraft


class DraftDAO:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    async def draft_for_operation(
        self,
        operation_id: UUID,
        *,
        owner_id: UUID | None = None,
    ) -> str | None:
        """Находит черновик операции только среди доступных владельцу цепочек."""
        statement = (
            select(Draft.id)
            .join(Thread, Thread.id == Draft.thread_id)
            .where(
                Draft.operation_id == operation_id,
                accessible_account(Thread.account_id, Thread.account_source, owner_id),
            )
        )

        async with self._session_factory() as session:
            draft_id = await session.scalar(statement)

        return str(draft_id) if draft_id is not None else None

    async def save_draft(
        self,
        data: DraftWrite,
        *,
        owner_id: UUID | None = None,
    ) -> str | None:
        """Создаёт черновик с проверкой доступа и дедупликацией по operation_id."""
        allowed_thread = (
            select(Thread.account_id, Thread.account_source)
            .where(
                Thread.id == data.thread_id,
                accessible_account(Thread.account_id, Thread.account_source, owner_id),
            )
        )
        statement = (
            insert(Draft)
            .values(
                id=uuid4(),
                operation_id=data.operation_id,
                thread_id=data.thread_id,
                recipient=data.recipient,
                subject=data.subject,
                text=data.text_content,
            )
            .on_conflict_do_nothing(index_elements=[Draft.operation_id])
            .returning(Draft.id)
        )

        async with self._session_factory.begin() as session:
            account = (await session.execute(allowed_thread)).one_or_none()
            if account is None or not await lock_accessible_account(
                session, account.account_id, account.account_source, owner_id,
            ):
                return None

            draft_id = await session.scalar(statement)

            if draft_id is None and data.operation_id is not None:
                draft_id = await session.scalar(
                    select(Draft.id).where(
                        Draft.operation_id == data.operation_id,
                        Draft.thread_id == data.thread_id,
                    )
                )

        return str(draft_id) if draft_id is not None else None

    async def list_drafts(
        self,
        *,
        owner_id: UUID | None = None,
        limit: int = 50,
    ) -> list[MailDraft]:
        """Возвращает последние черновики из доступных владельцу цепочек."""
        statement = (
            select(Draft)
            .join(Thread, Thread.id == Draft.thread_id)
            .where(
                accessible_account(Thread.account_id, Thread.account_source, owner_id),
            )
            .order_by(Draft.created_at.desc(), Draft.id.desc())
            .limit(limit)
        )

        async with self._session_factory() as session:
            drafts = await session.scalars(statement)

            return [
                MailDraft(
                    id=str(draft.id),
                    thread_id=str(draft.thread_id),
                    recipient=draft.recipient,
                    subject=draft.subject,
                    text=draft.text,
                    created_at=draft.created_at,
                )
                for draft in drafts
            ]
