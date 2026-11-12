from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import EmailThreadVector
from app.db.schemas import ThreadSearchResult


class RAGThreadRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def search(
        self,
        query_vector: list[float],
        top_k: int = 5,
    ) -> list[ThreadSearchResult]:
        """Семантический поиск по саммари email-тредов."""

        if top_k <= 0:
            return []

        distance = EmailThreadVector.embedding.cosine_distance(
            query_vector
        )

        stmt = (
            select(
                EmailThreadVector.id,
                EmailThreadVector.thread_id,
                EmailThreadVector.date,
                EmailThreadVector.content,
                distance.label("distance"),
            )
            .order_by(distance.asc())
            .limit(top_k)
        )

        async with self._session_factory() as session:
            result = await session.execute(stmt)

            return [
                ThreadSearchResult(
                    id=row.id,
                    thread_id=row.thread_id,
                    date=row.date,
                    content=row.content,
                    score=(
                        1.0 - float(row.distance)
                        if row.distance is not None
                        else None
                    ),
                )
                for row in result.all()
            ]

    async def upsert(
        self,
        thread_id: UUID,
        date: datetime,
        content: str,
        embedding: list[float],
    ) -> UUID:
        """Создает или обновляет векторное саммари треда в транзакции с commit."""

        insert_stmt = pg_insert(EmailThreadVector).values(
            id=uuid4(),
            thread_id=thread_id,
            date=date,
            content=content,
            embedding=embedding,
        )

        stmt = (
            insert_stmt.on_conflict_do_update(
                index_elements=[EmailThreadVector.thread_id],
                set_={
                    "date": insert_stmt.excluded.date,
                    "content": insert_stmt.excluded.content,
                    "embedding": insert_stmt.excluded.embedding,
                },
            )
            .returning(EmailThreadVector.id)
        )

        async with self._session_factory.begin() as session:
            result = await session.execute(stmt)
            vector_id = result.scalar_one()

        return vector_id
