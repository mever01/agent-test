from uuid import UUID

from sqlalchemy import literal, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import Exists, ScalarSelect

from app.db.enums import AccountSource, GmailConnectionStatus
from app.db.models import GmailAccount, GmailConnection

READABLE_CONNECTIONS = (
    GmailConnectionStatus.CONNECTED,
    GmailConnectionStatus.SYNCING,
    GmailConnectionStatus.SYNC_ERROR,
)


def accessible_account(
    account_id: ColumnElement[UUID],
    account_source: ColumnElement[AccountSource],
    owner_id: UUID | None,
) -> Exists:
    """Проверяет доступ по паре источника и аккаунта; неизвестные запрещены.

    Сейчас реализован Gmail. Новый провайдер должен добавить собственную
    проверку владельца и состояния подключения в этом модуле.
    """
    query = (
        select(GmailAccount.id)
        .outerjoin(GmailConnection)
        .where(
            account_source == AccountSource.GMAIL,
            GmailAccount.id == account_id,
        )
        .correlate_except(GmailAccount, GmailConnection)
    )
    if owner_id is None:
        query = query.where(GmailAccount.gmail_email.is_(None))
    else:
        query = query.where(
            GmailAccount.owner_id == owner_id,
            (
                GmailAccount.gmail_email.is_(None)
                | GmailConnection.status.in_(READABLE_CONNECTIONS)
            ),
        )
    return query.exists()


def mailbox_email(
    account_id: ColumnElement[UUID],
    account_source: ColumnElement[AccountSource],
) -> ScalarSelect[str | None]:
    """Возвращает адрес ящика, не добавляя JOIN провайдера в почтовый DAO."""
    return (
        select(GmailAccount.gmail_email)
        .where(
            account_source == AccountSource.GMAIL,
            GmailAccount.id == account_id,
        )
        .correlate_except(GmailAccount)
        .scalar_subquery()
    )


async def lock_mail_account(
    session: AsyncSession, account_id: UUID, account_source: AccountSource,
) -> bool:
    """Проверяет существование аккаунта и блокирует его до конца транзакции.

    Заменяет проверку FK на конкретную таблицу провайдера при записи почты.
    """
    query = select(GmailAccount.id).where(
        literal(account_source.value) == AccountSource.GMAIL.value,
        GmailAccount.id == account_id,
    )
    return await session.scalar(query.with_for_update()) is not None


async def lock_accessible_account(
    session: AsyncSession, account_id: UUID, account_source: AccountSource,
    owner_id: UUID | None,
) -> bool:
    """Блокирует аккаунт перед проверкой доступа и сохранением черновика.

    Блокировка согласована с OAuth и отключением: после ожидания повторно
    проверяет доступ отдельным запросом с актуальным состоянием подключения.
    """
    if not await lock_mail_account(session, account_id, account_source):
        return False
    query = select(accessible_account(
        literal(account_id), literal(account_source.value), owner_id,
    ))
    return bool(await session.scalar(query))
