import uuid
from datetime import datetime, date
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, text
from sqlalchemy.orm import selectinload
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.models import Thread, RawEmail, Draft
from app.schemas.email import EmailMessage, EmailSnippet, ThreadDetails


class EmailRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def search_emails(
        self,
        words: str,
        sender: str | None = None,
        start_date: date | datetime | None = None,
        end_date: date | datetime | None = None,
        limit: int = 10,
    ) -> list[EmailSnippet]:
        """
        Полнотекстовый (FTS) и триграммный поиск по письмам (SQLAlchemy Core).
        Возвращает ID письма и цепочки, тему, отправителя, дату и краткий фрагмент (snippet).
        """
        conditions = [
            """(
                tsv @@ plainto_tsquery('russian', :words)
                OR body ILIKE '%' || :words || '%'
                OR subject ILIKE '%' || :words || '%'
                OR thread_id ILIKE '%' || :words || '%'
                OR id ILIKE '%' || :words || '%'
            )"""
        ]
        params: dict[str, Any] = {"words": words, "limit": limit}

        if sender:
            conditions.append("sender ILIKE '%' || :sender || '%'")
            params["sender"] = sender

        if start_date:
            conditions.append("date >= CAST(:start_date AS DATE)")
            params["start_date"] = start_date

        if end_date:
            conditions.append("date < (CAST(:end_date AS DATE) + INTERVAL '1 day')")
            params["end_date"] = end_date

        where_clause = " AND ".join(conditions)

        query = text(f"""
            SELECT 
                id AS email_id,
                thread_id,
                subject,
                sender,
                date,
                ts_headline('russian', body, plainto_tsquery('russian', :words),
                            'StartSel=<b>, StopSel=</b>, MaxWords=35, MinWords=15') AS snippet
            FROM raw_emails
            WHERE {where_clause}
            ORDER BY date DESC
            LIMIT :limit
        """)
        result = await self.session.execute(query, params)
        rows = result.mappings().all()
        return [
            EmailSnippet(
                email_id=str(row["email_id"]),
                thread_id=str(row["thread_id"]),
                subject=row["subject"],
                sender=row["sender"],
                date=row["date"],
                snippet=row["snippet"] or row["subject"],
            )
            for row in rows
        ]

    async def get_thread_emails(self, thread_id: uuid.UUID) -> list[EmailMessage]:
        """Возвращает сообщения цепочки в хронологическом порядке через ORM."""
        stmt = (
            select(RawEmail)
            .where(RawEmail.thread_id == thread_id)
            .order_by(RawEmail.date.asc())
        )
        result = await self.session.scalars(stmt)
        return [
            EmailMessage(
                id=str(m.id),
                thread_id=str(m.thread_id),
                sender=m.sender,
                recipient=m.recipient,
                date=m.date,
                subject=m.subject,
                body=m.body,
            )
            for m in result.all()
        ]

    async def get_thread(self, thread_id: uuid.UUID) -> ThreadDetails | None:
        """Получение цепочки со всеми сообщениями через ORM (selectinload)."""
        stmt = (
            select(Thread)
            .options(selectinload(Thread.emails))
            .where(Thread.id == thread_id)
        )
        thread = (await self.session.scalars(stmt)).first()
        if not thread:
            return None

        return ThreadDetails(
            thread_id=str(thread.id),
            subject=thread.subject,
            client_email=thread.client_email,
            status=thread.status,
            messages=[
                EmailMessage(
                    id=str(m.id),
                    thread_id=str(m.thread_id),
                    sender=m.sender,
                    recipient=m.recipient,
                    date=m.date,
                    subject=m.subject,
                    body=m.body,
                )
                for m in thread.emails
            ],
        )

    async def save_draft(
        self,
        thread_id: uuid.UUID,
        recipient: str,
        subject: str,
        text_content: str,
    ) -> str:
        """Создание черновика ответа через ORM."""
        draft_id = uuid.uuid4()
        draft = Draft(
            id=draft_id,
            thread_id=thread_id,
            recipient=recipient,
            subject=subject,
            text=text_content,
        )
        self.session.add(draft)
        await self.session.commit()
        return str(draft_id)

    async def close_thread(self, thread_id: uuid.UUID) -> bool:
        """Переводит статус треда в 'closed' через ORM/Core."""
        stmt = (
            update(Thread)
            .where(Thread.id == thread_id)
            .values(status="closed")
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    async def upsert_thread(
        self,
        thread_id: uuid.UUID,
        subject: str,
        client_email: str,
        status: str = "active",
    ) -> None:
        """Вставка или обновление цепочки (PostgreSQL ON CONFLICT)."""
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
        await self.session.execute(stmt)
        await self.session.commit()

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
        """Вставка сырого письма (PostgreSQL ON CONFLICT DO NOTHING)."""
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
            .on_conflict_do_nothing(index_elements=[RawEmail.id])
        )
        await self.session.execute(stmt)
        await self.session.commit()
