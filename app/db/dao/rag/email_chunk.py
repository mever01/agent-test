from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.enums import AccountSource
from app.db.models import EmailChunk, GmailAccount, GmailConnection, RawEmail
from app.db.dao.query_helpers import READABLE_CONNECTIONS, accessible_account
from app.dto.db_mail import MailSearchCriteria, MailSnippet
from app.dto.rag import EmailIndexingJob, IndexedChunk


class EmailChunkDAO:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def pending_jobs(self, cutoff: datetime) -> list[EmailIndexingJob]:
        stmt = (
            select(RawEmail, GmailConnection.generation)
            .join(GmailAccount, GmailAccount.id == RawEmail.account_id)
            .outerjoin(GmailConnection)
            .where(
                RawEmail.account_source == AccountSource.GMAIL,
                RawEmail.rag_updated_at <= cutoff,
                or_(
                    RawEmail.rag_indexed_at.is_(None),
                    RawEmail.rag_indexed_at < RawEmail.rag_updated_at,
                ),
                or_(
                    GmailAccount.gmail_email.is_(None),
                    (
                        GmailConnection.synced_through_at.is_not(None)
                        & GmailConnection.status.in_(READABLE_CONNECTIONS)
                    ),
                ),
            )
            .order_by(RawEmail.rag_updated_at, RawEmail.id)
            .limit(10)
        )
        async with self._sessions() as session:
            return [
                EmailIndexingJob(
                    mail.id, mail.account_id, generation,
                    mail.rag_updated_at, mail.subject, mail.body,
                )
                for mail, generation in await session.execute(stmt)
            ]

    async def replace_chunks(
        self, job: EmailIndexingJob, chunks: list[IndexedChunk],
    ) -> bool:
        async with self._sessions.begin() as session:
            # Same lock order as Gmail synchronization and OAuth.
            account = await session.get(
                GmailAccount, job.account_id, with_for_update=True,
            )
            connection = await session.get(
                GmailConnection, job.account_id, with_for_update=True,
            )
            if account is None:
                return False
            if account.gmail_email is not None and (
                connection is None or connection.generation != job.generation
                or connection.status not in READABLE_CONNECTIONS
            ):
                return False
            mail = await session.get(RawEmail, job.email_id, with_for_update=True)
            if (
                mail is None or mail.account_source != AccountSource.GMAIL
                or mail.account_id != job.account_id
                or mail.rag_updated_at != job.updated_at
                or mail.rag_indexed_at == job.updated_at
            ):
                return False
            await session.execute(
                delete(EmailChunk).where(EmailChunk.email_id == job.email_id),
            )
            session.add_all([
                EmailChunk(
                    email_id=job.email_id, chunk_index=chunk.index,
                    content=chunk.content, embedding=chunk.embedding,
                )
                for chunk in chunks
            ])
            mail.rag_indexed_at = job.updated_at
            return True

    async def search(
        self, criteria: MailSearchCriteria, vector: list[float],
        owner_id: UUID | None, limit: int,
    ) -> list[MailSnippet]:
        distance = EmailChunk.embedding.cosine_distance(vector)
        stmt = (
            select(
                RawEmail.id, RawEmail.thread_id, RawEmail.subject,
                RawEmail.sender, RawEmail.date, EmailChunk.content,
                distance.label("distance"),
            )
            .join(RawEmail)
            .where(
                accessible_account(
                    RawEmail.account_id, RawEmail.account_source, owner_id,
                ),
                RawEmail.rag_indexed_at == RawEmail.rag_updated_at,
                distance < 0.6,
            )
        )
        if criteria.sender:
            sender = criteria.sender.lower()
            if "@" in sender:
                stmt = stmt.where(func.lower(RawEmail.sender) == sender)
            else:
                stmt = stmt.where(
                    func.strpos(func.lower(RawEmail.sender), sender) > 0,
                )
        if criteria.participant:
            participant = criteria.participant.lower()
            stmt = stmt.where(or_(
                func.lower(RawEmail.sender) == participant,
                func.lower(RawEmail.recipient) == participant,
            ))
        if criteria.start_date:
            stmt = stmt.where(RawEmail.date >= criteria.start_date)
        if criteria.end_date:
            stmt = stmt.where(RawEmail.date < criteria.end_date + timedelta(days=1))
        # Rank the best fragment of each message before applying the message limit.
        ranked = stmt.add_columns(
            func.row_number().over(
                partition_by=RawEmail.id, order_by=(distance, EmailChunk.chunk_index),
            ).label("fragment_rank"),
        ).subquery()
        query = (
            select(ranked)
            .where(ranked.c.fragment_rank == 1)
            .order_by(ranked.c.distance, ranked.c.id)
            .limit(limit)
        )
        async with self._sessions() as session:
            return [
                MailSnippet(
                    str(row.id), str(row.thread_id), row.subject,
                    row.sender, row.date, row.content[:240],
                )
                for row in await session.execute(query)
            ]
