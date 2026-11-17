import asyncio

from app.db.dao.rag.document_chunk import DocumentChunkDAO
from app.dto.rag import DocumentContent, DocumentFile, IndexedChunk
from app.external_api_clients.embedding_client import EmbeddingClient
from app.services.rag.ingestion.chunking import split_markdown_by_headers_or_size


class DocumentIngestionService:
    def __init__(self, dao: DocumentChunkDAO, embedding: EmbeddingClient) -> None:
        self._dao = dao
        self._embedding = embedding

    async def ingest_document(self, data: DocumentFile) -> int:
        """Читает файл вне event loop и индексирует его содержимое."""
        content = await asyncio.to_thread(data.file_path.read_text, encoding="utf-8")
        return await self.process_document(DocumentContent(
            data.doc_id, data.title, content,
        ))

    async def process_document(self, data: DocumentContent) -> int:
        """Готовит фрагменты документа и атомарно заменяет его индекс."""
        text = split_markdown_by_headers_or_size(data.content)
        if not text:
            raise ValueError(f"Document {data.doc_id} has no content to index")
        vectors = await self._embedding.get_embeddings(text)
        chunks = [
            IndexedChunk(index, content, vector)
            for index, (content, vector) in enumerate(
                zip(text, vectors, strict=True), start=1,
            )
        ]
        await self._dao.replace_chunks(data.doc_id, data.title, chunks)
        return len(chunks)
