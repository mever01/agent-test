from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from uuid import UUID

from sqlalchemy import or_, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.elements import ColumnElement

from app.db.enums import AccountSource, GmailConnectionStatus
from app.db.models import GmailAccount, GmailConnection, RawEmail, Thread
from app.dto.gmail import (
    GmailAccountData,
    GmailConnectionData,
    GmailSyncLease,
    ImportedGmailMessage,
    ImportedGmailThread,
)


class GmailDAO:
    """Выполняет запросы Gmail в транзакциях, которыми управляет сервис."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        """Сохраняет фабрику сессий для открытия транзакций."""
        self._sessions = sessions

    def transaction(self) -> AbstractAsyncContextManager[AsyncSession]:
        """Открывает сессию с коммитом при успехе и откатом при исключении."""
        return self._sessions.begin()

    @staticmethod
    async def create_account(
        session: AsyncSession, owner_id: UUID, name: str,
    ) -> GmailAccountData:
        """Создаёт аккаунт владельца и возвращает его данные без коммита."""
        account = GmailAccount(owner_id=owner_id, name=name)
        session.add(account)
        await session.flush()
        return GmailAccountData.model_validate(account)

    @staticmethod
    async def list_accounts(
        session: AsyncSession, owner_id: UUID,
    ) -> list[tuple[GmailAccountData, GmailConnectionData | None]]:
        """Возвращает аккаунты владельца с подключениями, скрывая демоданные."""
        statement = (
            select(GmailAccount, GmailConnection)
            .outerjoin(GmailConnection)
            .where(GmailAccount.owner_id == owner_id, _manageable_account())
            .order_by(GmailAccount.created_at, GmailAccount.id)
        )
        return [
            (
                GmailAccountData.model_validate(account),
                GmailConnectionData.model_validate(connection) if connection else None,
            )
            for account, connection in await session.execute(statement)
        ]

    @staticmethod
    async def lock_account(
        session: AsyncSession, account_id: UUID,
        *, owner_id: UUID | None = None,
    ) -> GmailAccountData | None:
        """Блокирует аккаунт до конца транзакции для согласованных изменений.

        Если передан владелец, проверяет принадлежность и скрывает демоданные.
        Возвращает None, если подходящего аккаунта нет.
        """
        statement = select(GmailAccount).where(GmailAccount.id == account_id)
        if owner_id is not None:
            statement = statement.where(
                GmailAccount.owner_id == owner_id, _manageable_account(),
            )
        account = await session.scalar(statement.with_for_update())
        return GmailAccountData.model_validate(account) if account else None

    @staticmethod
    async def lock_connection(
        session: AsyncSession, account_id: UUID,
    ) -> GmailConnectionData | None:
        """Блокирует подключение до конца транзакции; при отсутствии вернёт None."""
        connection = await session.get(
            GmailConnection, account_id, with_for_update=True,
        )
        return GmailConnectionData.model_validate(connection) if connection else None

    @staticmethod
    async def create_connection(
        session: AsyncSession, account_id: UUID,
    ) -> GmailConnectionData:
        """Создаёт подключение аккаунта с начальными значениями из модели БД."""
        connection = GmailConnection(gmail_account_id=account_id)
        session.add(connection)
        await session.flush()
        return GmailConnectionData.model_validate(connection)

    @staticmethod
    async def save_account(
        session: AsyncSession, account: GmailAccountData,
    ) -> None:
        """Сохраняет адрес Gmail после успешной авторизации аккаунта."""
        await session.execute(
            update(GmailAccount).where(GmailAccount.id == account.id)
            .values(gmail_email=account.gmail_email),
        )

    @staticmethod
    async def save_connection(
        session: AsyncSession, connection: GmailConnectionData,
    ) -> None:
        """Записывает изменения DTO подключения в текущей транзакции."""
        await session.execute(
            update(GmailConnection)
            .where(GmailConnection.gmail_account_id == connection.gmail_account_id)
            .values(**connection.model_dump(exclude={"gmail_account_id"})),
        )

    @staticmethod
    async def lock_oauth_attempt(
        session: AsyncSession, state_digest: str,
        browser_digest: str, now: datetime,
    ) -> GmailConnectionData | None:
        """Блокирует действующую OAuth-попытку, начатую в этом браузере.

        Сервис должен погасить попытку в той же транзакции, чтобы повторный
        callback не использовал её снова. При несовпадении или истечении
        срока возвращает None.
        """
        statement = select(GmailConnection).where(
            GmailConnection.oauth_state_digest == state_digest,
            GmailConnection.oauth_browser_digest == browser_digest,
            GmailConnection.oauth_expires_at > now,
        )
        connection = await session.scalar(statement.with_for_update())
        return GmailConnectionData.model_validate(connection) if connection else None

    @staticmethod
    async def lock_due_connection(
        session: AsyncSession, now: datetime,
        statuses: Sequence[GmailConnectionStatus],
    ) -> tuple[GmailConnectionData, str] | None:
        """Выбирает готовое к синхронизации подключение и адрес почты.

        Пропускает строки, заблокированные другими воркерами. Сервис должен
        оформить аренду до завершения транзакции. Если подходящих строк нет,
        возвращает None.
        """
        statement = (
            select(GmailConnection, GmailAccount.gmail_email)
            .join(GmailAccount)
            .where(
                GmailAccount.gmail_email.is_not(None),
                GmailConnection.client_id.is_not(None),
                GmailConnection.client_secret_ciphertext.is_not(None),
                GmailConnection.refresh_token_ciphertext.is_not(None),
                GmailConnection.status.in_(statuses),
                GmailConnection.next_sync_at <= now,
                or_(
                    GmailConnection.lease_expires_at.is_(None),
                    GmailConnection.lease_expires_at <= now,
                ),
            )
            .order_by(GmailConnection.next_sync_at, GmailConnection.gmail_account_id)
            .limit(1)
            .with_for_update(of=GmailConnection, skip_locked=True)
        )
        row = (await session.execute(statement)).one_or_none()
        if row is None:
            return None
        return GmailConnectionData.model_validate(row[0]), row[1]

    @staticmethod
    async def lock_sync_connection(
        session: AsyncSession, lease: GmailSyncLease, now: datetime,
    ) -> GmailConnectionData | None:
        """Блокирует подключение, если аренда воркера ещё действительна.

        Токен, поколение, статус и срок аренды защищают от записи результатов
        устаревшего запуска после отключения или повторного подключения.
        Если воркер потерял аренду, возвращает None.
        """
        statement = select(GmailConnection).where(
            GmailConnection.gmail_account_id == lease.account_id,
            GmailConnection.lease_token == lease.token,
            GmailConnection.generation == lease.generation,
            GmailConnection.status == GmailConnectionStatus.SYNCING,
            GmailConnection.lease_expires_at > now,
        )
        connection = await session.scalar(statement.with_for_update())
        return GmailConnectionData.model_validate(connection) if connection else None

    @staticmethod
    async def existing_message_ids(
        session: AsyncSession, account_id: UUID, message_ids: list[str],
    ) -> set[str]:
        """Возвращает уже сохранённые ID из переданного списка писем аккаунта."""
        if not message_ids:
            return set()
        statement = select(RawEmail.message_id).where(
            RawEmail.account_source == AccountSource.GMAIL,
            RawEmail.account_id == account_id,
            RawEmail.message_id.in_(message_ids),
        )
        return set(await session.scalars(statement))

    @staticmethod
    async def upsert_thread(
        session: AsyncSession, account_id: UUID,
        thread: ImportedGmailThread, now: datetime,
    ) -> UUID:
        """Создаёт или обновляет цепочку по Gmail ID, сохраняя её статус."""
        statement = insert(Thread).values(
            account_source=AccountSource.GMAIL,
            account_id=account_id,
            external_thread_id=thread.gmail_thread_id,
            subject=thread.subject,
            client_email=thread.client_email,
        )
        statement = statement.on_conflict_do_update(
            constraint="uq_threads_external_thread",
            set_={
                "subject": statement.excluded.subject,
                "client_email": statement.excluded.client_email,
                "updated_at": now,
            },
        ).returning(Thread.id)
        return (await session.scalars(statement)).one()

    @staticmethod
    async def upsert_messages(
        session: AsyncSession, account_id: UUID, thread_id: UUID,
        messages: list[ImportedGmailMessage], now: datetime,
    ) -> None:
        """Сохраняет пакет писем без дублей при повторном импорте.

        Обновляет rag_updated_at только при изменении содержимого или
        принадлежности к цепочке, чтобы не запускать лишнюю индексацию.
        """
        if not messages:
            return
        statement = insert(RawEmail).values([
            {
                "account_source": AccountSource.GMAIL,
                "thread_id": thread_id,
                "account_id": account_id,
                "message_id": message.gmail_message_id,
                "sender": message.sender,
                "recipient": message.recipient,
                "date": message.date,
                "subject": message.subject,
                "body": message.body,
                "rag_updated_at": now,
            }
            for message in messages
        ])
        previous = tuple_(
            RawEmail.thread_id, RawEmail.sender, RawEmail.recipient,
            RawEmail.date, RawEmail.subject, RawEmail.body,
        )
        incoming = statement.excluded
        updated = tuple_(
            incoming.thread_id, incoming.sender, incoming.recipient,
            incoming.date, incoming.subject, incoming.body,
        )
        await session.execute(statement.on_conflict_do_update(
            constraint="uq_raw_emails_external_message",
            set_={
                "thread_id": incoming.thread_id,
                "sender": incoming.sender,
                "recipient": incoming.recipient,
                "date": incoming.date,
                "subject": incoming.subject,
                "body": incoming.body,
                "rag_updated_at": now,
            },
            where=previous.is_distinct_from(updated),
        ))


def _manageable_account() -> ColumnElement[bool]:
    """Исключает демоаккаунты с письмами, но без подключённого адреса Gmail."""
    contains_mail = select(Thread.id).where(
        Thread.account_source == AccountSource.GMAIL,
        Thread.account_id == GmailAccount.id,
    ).exists()
    return GmailAccount.gmail_email.is_not(None) | ~contains_mail
