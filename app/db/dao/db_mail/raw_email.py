import re
from datetime import timedelta
from uuid import UUID

from sqlalchemy import Date, String, cast, func, literal_column, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.dao.query_helpers import accessible_account, lock_mail_account
from app.db.models import RawEmail
from app.dto.db_mail import EmailWrite, MailMessage, MailSearchCriteria, MailSnippet


class RawEmailDAO:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    async def get_email(
        self, email_id: UUID, *, owner_id: UUID,
    ) -> MailMessage | None:
        """Читает одно письмо из доступного владельцу аккаунта."""
        statement = select(RawEmail).where(
            RawEmail.id == email_id,
            accessible_account(
                RawEmail.account_id, RawEmail.account_source, owner_id,
            ),
        )
        async with self._session_factory() as session:
            email = await session.scalar(statement)
            return _to_mail_message(email) if email is not None else None

    async def search_emails(
        self,
        criteria: MailSearchCriteria,
        *,
        owner_id: UUID | None = None,
        limit: int = 10,
    ) -> list[MailSnippet]:
        """Ищет доступные письма по тексту, участникам и диапазону дат."""
        conditions = [
            accessible_account(RawEmail.account_id, RawEmail.account_source, owner_id),
        ]
        snippet = func.left(RawEmail.body, 240)

        if criteria.words:
            config = literal_column("'russian'::regconfig")
            query = func.plainto_tsquery(config, criteria.words)
            words = criteria.words.lower()

            conditions.append(
                or_(
                    RawEmail.tsv.bool_op("@@")(query),
                    func.strpos(func.lower(RawEmail.body), words) > 0,
                    func.strpos(func.lower(RawEmail.subject), words) > 0,
                    func.strpos(
                        func.lower(cast(RawEmail.thread_id, String)),
                        words,
                    ) > 0,
                    func.strpos(
                        func.lower(cast(RawEmail.id, String)),
                        words,
                    ) > 0,
                )
            )
            snippet = func.ts_headline(
                config,
                RawEmail.body,
                query,
                "StartSel=<b>, StopSel=</b>, MaxWords=35, MinWords=15",
            )

        if criteria.sender:
            sender = criteria.sender.lower()

            if re.fullmatch(r"[^\s@]+@[^\s@]+", sender):
                conditions.append(func.lower(RawEmail.sender) == sender)
            else:
                conditions.append(
                    func.strpos(func.lower(RawEmail.sender), sender) > 0,
                )

        if criteria.participant:
            participant = criteria.participant.lower()
            conditions.append(
                or_(
                    func.lower(RawEmail.sender) == participant,
                    func.lower(RawEmail.recipient) == participant,
                )
            )

        if criteria.start_date is not None:
            conditions.append(
                RawEmail.date >= cast(criteria.start_date, Date),
            )

        if criteria.end_date is not None:
            conditions.append(
                RawEmail.date < cast(
                    criteria.end_date + timedelta(days=1),
                    Date,
                ),
            )

        statement = (
            select(
                RawEmail.id,
                RawEmail.thread_id,
                RawEmail.subject,
                RawEmail.sender,
                RawEmail.date,
                snippet.label("snippet"),
            )
            .where(*conditions)
            .order_by(RawEmail.date.desc(), RawEmail.id.desc())
            .limit(limit)
        )

        async with self._session_factory() as session:
            rows = await session.execute(statement)

            return [
                MailSnippet(
                    email_id=str(row.id),
                    thread_id=str(row.thread_id),
                    subject=row.subject,
                    sender=row.sender,
                    date=row.date,
                    snippet=row.snippet or row.subject,
                )
                for row in rows
            ]

    async def get_thread_emails(
        self,
        thread_id: UUID,
        *,
        owner_id: UUID | None = None,
    ) -> list[MailMessage]:
        """Возвращает письма доступной цепочки в хронологическом порядке."""
        statement = (
            select(RawEmail)
            .where(
                RawEmail.thread_id == thread_id,
                accessible_account(
                    RawEmail.account_id, RawEmail.account_source, owner_id,
                ),
            )
            .order_by(RawEmail.date, RawEmail.id)
        )

        async with self._session_factory() as session:
            emails = await session.scalars(statement)

            return [_to_mail_message(email) for email in emails]

    async def insert_email(self, data: EmailWrite) -> None:
        """Проверяет аккаунт и сохраняет письмо; повтор того же UUID пропускает."""
        statement = (
            insert(RawEmail)
            .values(
                id=data.email_id,
                thread_id=data.thread_id,
                account_source=data.account_source,
                account_id=data.account_id,
                message_id=data.message_id,
                sender=data.sender,
                recipient=data.recipient,
                date=data.date,
                subject=data.subject,
                body=data.body,
            )
            .on_conflict_do_nothing(index_elements=[RawEmail.id])
        )

        async with self._session_factory.begin() as session:
            if not await lock_mail_account(
                session, data.account_id, data.account_source,
            ):
                raise ValueError("Почтовый аккаунт не найден.")
            await session.execute(statement)


def _to_mail_message(email: RawEmail) -> MailMessage:
    return MailMessage(
        id=str(email.id),
        thread_id=str(email.thread_id),
        sender=email.sender,
        recipient=email.recipient,
        date=email.date,
        subject=email.subject,
        body=email.body,
    )
