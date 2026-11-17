from app.db.dao.rag.document_chunk import DocumentChunkDAO
from app.dto.rag import RAGContextResult
from app.external_api_clients.embedding_client import EmbeddingClient
from app.services.rag.retrieval.document.formatting import (
    document_to_chunk,
    format_document_context,
)
from app.services.rag.retrieval.document.prompts import QUERY_EMBEDDING_INSTRUCTION


class DocumentRetrievalService:
    def __init__(
        self, dao: DocumentChunkDAO, embedding: EmbeddingClient, top_k: int = 5,
    ) -> None:
        if top_k < 0:
            raise ValueError("top_k must be non-negative")
        self._dao = dao
        self._embedding = embedding
        self._top_k = top_k

    async def get_context(
        self, query: str, top_k_docs: int | None = None,
    ) -> RAGContextResult:
        """Находит документы об условиях компании для ответа по переписке."""
        if not query.strip():
            raise ValueError("Query must not be empty")
        limit = self._top_k if top_k_docs is None else top_k_docs
        if limit < 0:
            raise ValueError("top_k must be non-negative")
        if limit == 0:
            return RAGContextResult()
        vector = await self._embedding.get_embedding(
            query, instruction=QUERY_EMBEDDING_INSTRUCTION,
        )
        results = await self._dao.search(vector, top_k=limit)
        documents = [document_to_chunk(item) for item in results]
        return RAGContextResult(
            documents=documents,
            formatted_context=format_document_context(documents),
            used_document_ids=list(dict.fromkeys(doc.source_id for doc in documents)),
        )
