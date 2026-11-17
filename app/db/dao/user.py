from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.user import User


class UserRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def by_email(self, email: str) -> User | None:
        async with self._sessions() as session:
            return await session.scalar(select(User).where(User.email == email))

    async def by_id(self, user_id: UUID) -> User | None:
        async with self._sessions() as session:
            return await session.get(User, user_id)

    async def add(self, user: User) -> None:
        async with self._sessions.begin() as session:
            session.add(user)

    async def add_seed_manager(self, email: str, password_hash: str) -> None:
        statement = (
            insert(User)
            .values(email=email, role="manager", password_hash=password_hash)
            .on_conflict_do_nothing(index_elements=[User.email])
        )
        async with self._sessions.begin() as session:
            await session.execute(statement)
