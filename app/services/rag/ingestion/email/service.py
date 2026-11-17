from app.db.dao.rag.email_chunk import EmailChunkDAO
from app.dto.rag import EmailIndexingJob, IndexedChunk
from app.external_api_clients.embedding_client import EmbeddingClient
from app.services.rag.ingestion.email.chunking import prepare_email_fragments


class EmailIngestionService:
    def __init__(self, dao: EmailChunkDAO, embedding: EmbeddingClient) -> None:
        self._dao = dao
        self._embedding = embedding

    async def process_email(self, job: EmailIndexingJob) -> bool:
        """Индексирует версию письма без LLM-суммаризации всей цепочки."""
        text = prepare_email_fragments(job.subject, job.body)
        vectors = await self._embedding.get_embeddings(text) if text else []
        chunks = [
            IndexedChunk(index, content, vector)
            for index, (content, vector) in enumerate(zip(text, vectors, strict=True))
        ]
        return await self._dao.replace_chunks(job, chunks)
