import uuid
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.models import DocumentChunk, EmailThreadVector
from app.schemas.rag import RagChunk

class VectorRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def search_documents(
        self,
        query_vector: list[float],
        top_k: int = 2,
    ) -> list[RagChunk]:
        """Семантический поиск по регламентам компании (SQLAlchemy ORM + pgvector)."""
        stmt = (
            select(
                DocumentChunk,
                (1 - DocumentChunk.embedding.cosine_distance(query_vector)).label("similarity_score"),
            )
            .order_by(DocumentChunk.embedding.cosine_distance(query_vector).asc())
            .limit(top_k)
        )
        result = await self.session.execute(stmt)
        rows = result.all()
        return [
            RagChunk(
                id=str(doc.id),
                source_type="company_doc",
                source_id=doc.doc_id,
                content=f"[{doc.title}, Чанк {doc.chunk_index}]\n{doc.content}",
                score=float(score) if score is not None else None,
            )
            for doc, score in rows
        ]

    async def search_threads(
        self,
        query_vector: list[float],
        top_k: int = 2,
    ) -> list[RagChunk]:
        """Семантический поиск по сжатым прошлым тредам (SQLAlchemy ORM + pgvector)."""
        stmt = (
            select(
                EmailThreadVector,
                (1 - EmailThreadVector.embedding.cosine_distance(query_vector)).label("similarity_score"),
            )
            .order_by(EmailThreadVector.embedding.cosine_distance(query_vector).asc())
            .limit(top_k)
        )
        result = await self.session.execute(stmt)
        rows = result.all()
        return [
            RagChunk(
                id=str(tv.id),
                source_type="thread_summary",
                source_id=str(tv.thread_id),
                thread_id=str(tv.thread_id),
                date=tv.date,
                content=f"[Архив треда: {tv.thread_id} от {tv.date.strftime('%Y-%m-%d')}]\n{tv.content}",
                score=float(score) if score is not None else None,
            )
            for tv, score in rows
        ]

    async def save_document_chunks(
        self,
        doc_id: str,
        title: str,
        chunks: list[tuple[int, str, list[float]]], # (chunk_index, content, embedding)
    ) -> None:
        """Атомарная перезапись чанков документа через ORM."""
        # 1. Удаляем старые чанки
        await self.session.execute(
            delete(DocumentChunk).where(DocumentChunk.doc_id == doc_id)
        )
        # 2. Вставляем новые чанки через ORM
        new_chunks = [
            DocumentChunk(
                id=uuid.uuid4(),
                doc_id=doc_id,
                title=title,
                chunk_index=chunk_idx,
                content=content,
                embedding=embedding,
            )
            for chunk_idx, content, embedding in chunks
        ]
        self.session.add_all(new_chunks)
        await self.session.commit()

    async def upsert_thread_vector(
        self,
        thread_id: uuid.UUID,
        date: datetime,
        content: str,
        embedding: list[float],
    ) -> str:
        """Вставка или обновление вектора саммари треда (PostgreSQL ON CONFLICT)."""
        vec_id = uuid.uuid4()
        stmt = (
            pg_insert(EmailThreadVector)
            .values(
                id=vec_id,
                thread_id=thread_id,
                date=date,
                content=content,
                embedding=embedding,
            )
            .on_conflict_do_update(
                index_elements=[EmailThreadVector.thread_id],
                set_={
                    "date": date,
                    "content": content,
                    "embedding": embedding,
                },
            )
        )
        await self.session.execute(stmt)
        await self.session.commit()
        return str(vec_id)
