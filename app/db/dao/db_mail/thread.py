from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.db.dao.query_helpers import (
    accessible_account,
    lock_mail_account,
    mailbox_email,
)
from app.db.models import RawEmail, Thread
from app.dto.db_mail import MailMessage, MailThreadDetails, ThreadWrite


class ThreadDAO:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    async def get_thread(
        self,
        thread_id: UUID,
        *,
        owner_id: UUID | None = None,
    ) -> MailThreadDetails | None:
        """Возвращает цепочку с письмами, проверяя владельца и источник аккаунта."""
        statement = (
            select(
                Thread,
                mailbox_email(Thread.account_id, Thread.account_source),
            )
            .options(selectinload(Thread.emails))
            .where(
                Thread.id == thread_id,
                accessible_account(Thread.account_id, Thread.account_source, owner_id),
            )
        )

        async with self._session_factory() as session:
            row = (await session.execute(statement)).one_or_none()

            if row is None:
                return None

            thread, mailbox_address = row
            messages = [
                MailMessage(
                    id=str(email.id),
                    thread_id=str(email.thread_id),
                    sender=email.sender,
                    recipient=email.recipient,
                    date=email.date,
                    subject=email.subject,
                    body=email.body,
                )
                for email in sorted(
                    thread.emails,
                    key=lambda email: (email.date, email.id),
                )
            ]

            return MailThreadDetails(
                thread_id=str(thread.id),
                subject=thread.subject,
                client_email=thread.client_email,
                messages=messages,
                mailbox_email=mailbox_address,
            )

    async def upsert_thread(self, data: ThreadWrite) -> None:
        """Сохраняет цепочку, запрещая смену её аккаунта и внешнего ID."""
        insertion = insert(Thread).values(
            id=data.thread_id,
            account_source=data.account_source,
            account_id=data.account_id,
            external_thread_id=data.external_thread_id,
            subject=data.subject,
            client_email=data.client_email,
        )
        statement = insertion.on_conflict_do_update(
            index_elements=[Thread.id],
            set_={
                "subject": insertion.excluded.subject,
                "client_email": insertion.excluded.client_email,
                "updated_at": func.now(),
            },
            where=(
                (Thread.account_source == data.account_source)
                & (Thread.account_id == data.account_id)
                & (Thread.external_thread_id == data.external_thread_id)
            ),
        ).returning(Thread.id)

        async with self._session_factory.begin() as session:
            if not await lock_mail_account(
                session, data.account_id, data.account_source,
            ):
                raise ValueError("Почтовый аккаунт не найден.")
            if await session.scalar(statement) is None:
                raise ValueError(
                    "Цепочка уже принадлежит другому аккаунту или источнику.",
                )

    async def thread_activity(
        self,
        thread_ids: list[UUID],
        *,
        owner_id: UUID | None = None,
    ) -> dict[UUID, datetime]:
        """Возвращает даты последних писем доступных цепочек."""
        if not thread_ids:
            return {}

        statement = (
            select(RawEmail.thread_id, func.max(RawEmail.date))
            .where(
                RawEmail.thread_id.in_(thread_ids),
                accessible_account(
                    RawEmail.account_id, RawEmail.account_source, owner_id,
                ),
            )
            .group_by(RawEmail.thread_id)
        )

        async with self._session_factory() as session:
            return dict((await session.execute(statement)).all())
