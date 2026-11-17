from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import DocumentChunk
from app.dto.rag import DocumentSearchResult, IndexedChunk


class DocumentChunkDAO:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def search(
        self,
        query_vector: list[float],
        top_k: int = 5,
    ) -> list[DocumentSearchResult]:
        """Семантический поиск по чанкам документов."""

        if top_k <= 0:
            return []

        distance = DocumentChunk.embedding.cosine_distance(
            query_vector
        )

        stmt = (
            select(
                DocumentChunk.id,
                DocumentChunk.doc_id,
                DocumentChunk.title,
                DocumentChunk.chunk_index,
                DocumentChunk.content,
                distance.label("distance"),
            )
            .order_by(distance.asc())
            .limit(top_k)
        )

        async with self._session_factory() as session:
            result = await session.execute(stmt)

            return [
                DocumentSearchResult(
                    id=row.id,
                    doc_id=row.doc_id,
                    title=row.title,
                    chunk_index=row.chunk_index,
                    content=row.content,
                    score=(
                        1.0 - float(row.distance)
                        if row.distance is not None
                        else None
                    ),
                )
                for row in result.all()
            ]

    async def replace_chunks(
        self,
        doc_id: str,
        title: str,
        chunks: list[IndexedChunk],
    ) -> None:
        """Заменяет все чанки документа в единой транзакции с commit."""

        new_chunks = [
            DocumentChunk(
                id=uuid4(),
                doc_id=doc_id,
                title=title,
                chunk_index=chunk.index,
                content=chunk.content,
                embedding=chunk.embedding,
            )
            for chunk in chunks
        ]

        async with self._session_factory.begin() as session:
            await session.execute(
                delete(DocumentChunk).where(
                    DocumentChunk.doc_id == doc_id
                )
            )
            session.add_all(new_chunks)
