
import re
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.db.models import Draft, RawEmail, Thread
from app.db.schemas import (
    MailDraft,
    MailMessage,
    MailSearchCriteria,
    MailSnippet,
    MailThreadDetails,
)


class MailRepository:
    """Репозиторий для работы с почтовыми тредами, письмами и черновиками."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    # -------------------------------------------------------------------------
    # Thread
    # -------------------------------------------------------------------------

    async def get_thread(
        self,
        thread_id: uuid.UUID,
    ) -> MailThreadDetails | None:
        """Возвращает тред с письмами в хронологическом порядке."""

        stmt = (
            select(Thread)
            .options(selectinload(Thread.emails))
            .where(Thread.id == thread_id)
        )

        async with self._session_factory() as session:
            thread = (await session.scalars(stmt)).one_or_none()

            if thread is None:
                return None

            thread: Thread

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
                status=thread.status,
                messages=messages,
            )

    async def close_thread(
        self,
        thread_id: uuid.UUID,
    ) -> bool:
        """Переводит тред в статус closed."""

        stmt = (
            update(Thread)
            .where(Thread.id == thread_id)
            .values(status="closed")
        )

        async with self._session_factory.begin() as session:
            result = await session.execute(stmt)
            updated = result.rowcount > 0

        return updated

    async def upsert_thread(
        self,
        thread_id: uuid.UUID,
        subject: str,
        client_email: str,
        status: str = "active",
    ) -> None:
        """Создает или обновляет тред."""

        stmt = (
            pg_insert(Thread)
            .values(
                id=thread_id,
                subject=subject,
                client_email=client_email,
                status=status,
            )
            .on_conflict_do_update(
                index_elements=[Thread.id],
                set_={
                    "subject": subject,
                    "client_email": client_email,
                    "status": status,
                    "updated_at": func.now(),
                },
            )
        )

        async with self._session_factory.begin() as session:
            await session.execute(stmt)

    # -------------------------------------------------------------------------
    # RawEmail
    # -------------------------------------------------------------------------

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
        """Выполняет полнотекстовый и текстовый поиск по письмам."""

        criteria = MailSearchCriteria(
            words=words,
            sender=sender,
            participant=participant,
            start_date=start_date.date() if isinstance(start_date, datetime) else start_date,
            end_date=end_date.date() if isinstance(end_date, datetime) else end_date,
        )
        conditions: list[str] = []
        params: dict[str, Any] = {"limit": limit}
        snippet_sql = "left(body, 240)"
        if criteria.words:
            conditions.append(
                """(
                    tsv @@ plainto_tsquery('russian', :words)
                    OR position(lower(:words) in lower(body)) > 0
                    OR position(lower(:words) in lower(subject)) > 0
                    OR position(lower(:words) in CAST(thread_id AS TEXT)) > 0
                    OR position(lower(:words) in CAST(id AS TEXT)) > 0
                )"""
            )
            snippet_sql = """ts_headline(
                'russian', body, plainto_tsquery('russian', :words),
                'StartSel=<b>, StopSel=</b>, MaxWords=35, MinWords=15'
            )"""
            params["words"] = criteria.words

        if criteria.sender:
            if re.fullmatch(r"[^\s@]+@[^\s@]+", criteria.sender):
                conditions.append("lower(sender) = lower(:sender)")
            else:
                conditions.append("position(lower(:sender) in lower(sender)) > 0")
            params["sender"] = criteria.sender

        if criteria.participant:
            conditions.append(
                "(lower(sender) = lower(:participant) OR lower(recipient) = lower(:participant))"
            )
            params["participant"] = criteria.participant

        if criteria.start_date is not None:
            conditions.append(
                "date >= CAST(:start_date AS DATE)"
            )
            params["start_date"] = criteria.start_date

        if criteria.end_date is not None:
            conditions.append(
                "date < (CAST(:end_date AS DATE) + INTERVAL '1 day')"
            )
            params["end_date"] = criteria.end_date

        where_clause = " AND ".join(conditions)

        stmt = text(f"""
            SELECT
                id AS email_id,
                thread_id,
                subject,
                sender,
                date,
                {snippet_sql} AS snippet
            FROM raw_emails
            WHERE {where_clause}
            ORDER BY date DESC, id DESC
            LIMIT :limit
        """)

        async with self._session_factory() as session:
            result = await session.execute(stmt, params)
            rows = result.mappings().all()

        return [
            MailSnippet(
                email_id=str(row["email_id"]),
                thread_id=str(row["thread_id"]),
                subject=row["subject"],
                sender=row["sender"],
                date=row["date"],
                snippet=row["snippet"] or row["subject"],
            )
            for row in rows
        ]

    async def get_thread_emails(
        self,
        thread_id: uuid.UUID,
    ) -> list[MailMessage]:
        """Возвращает письма треда в хронологическом порядке."""

        stmt = (
            select(RawEmail)
            .where(RawEmail.thread_id == thread_id)
            .order_by(
                RawEmail.date.asc(),
                RawEmail.id.asc(),
            )
        )

        async with self._session_factory() as session:
            result = await session.scalars(stmt)

            return [
                MailMessage(
                    id=str(email.id),
                    thread_id=str(email.thread_id),
                    sender=email.sender,
                    recipient=email.recipient,
                    date=email.date,
                    subject=email.subject,
                    body=email.body,
                )
                for email in result.all()
            ]

    async def insert_email(
        self,
        email_id: uuid.UUID,
        thread_id: uuid.UUID,
        sender: str,
        recipient: str,
        date: datetime,
        subject: str,
        body: str,
    ) -> None:
        """Вставляет письмо, игнорируя конфликт по ID."""

        stmt = (
            pg_insert(RawEmail)
            .values(
                id=email_id,
                thread_id=thread_id,
                sender=sender,
                recipient=recipient,
                date=date,
                subject=subject,
                body=body,
            )
            .on_conflict_do_nothing(
                index_elements=[RawEmail.id]
            )
        )

        async with self._session_factory.begin() as session:
            await session.execute(stmt)

    # -------------------------------------------------------------------------
    # Draft
    # -------------------------------------------------------------------------

    async def draft_for_operation(self, operation_id: uuid.UUID) -> str | None:
        async with self._session_factory() as session:
            draft_id = await session.scalar(
                select(Draft.id).where(Draft.operation_id == operation_id)
            )
        return str(draft_id) if draft_id else None

    async def save_draft(
        self,
        thread_id: uuid.UUID,
        recipient: str,
        subject: str,
        text_content: str,
        operation_id: uuid.UUID | None = None,
    ) -> str:
        """Создает черновик ответа."""

        draft_id = uuid.uuid4()

        if operation_id is not None:
            statement = (
                pg_insert(Draft)
                .values(
                    id=draft_id, operation_id=operation_id, thread_id=thread_id,
                    recipient=recipient, subject=subject, text=text_content,
                )
                .on_conflict_do_nothing(index_elements=[Draft.operation_id])
                .returning(Draft.id)
            )
            async with self._session_factory.begin() as session:
                existing_id = await session.scalar(statement)
                if existing_id is None:
                    result = await session.scalars(
                        select(Draft.id).where(Draft.operation_id == operation_id)
                    )
                    existing_id = result.one()
            return str(existing_id)

        draft = Draft(
            id=draft_id,
            thread_id=thread_id,
            recipient=recipient,
            subject=subject,
            text=text_content,
        )

        async with self._session_factory.begin() as session:
            session.add(draft)

        return str(draft_id)

    async def list_drafts(
        self,
        limit: int = 50,
    ) -> list[MailDraft]:
        """Возвращает последние созданные черновики."""

        stmt = (
            select(Draft)
            .order_by(
                Draft.created_at.desc(),
                Draft.id.desc(),
            )
            .limit(limit)
        )

        async with self._session_factory() as session:
            result = await session.scalars(stmt)

            return [
                MailDraft(
                    id=str(draft.id),
                    thread_id=str(draft.thread_id),
                    recipient=draft.recipient,
                    subject=draft.subject,
                    text=draft.text,
                    created_at=draft.created_at,
                )
                for draft in result.all()
            ]
