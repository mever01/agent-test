
from core.utils.mixins.logger import LoggerMixin

from app.db.repositories.rag_document_repository import RAGDocumentRepository
from app.db.repositories.rag_thread_repository import RAGThreadRepository
from app.db.schemas import DocumentSearchResult, ThreadSearchResult
from app.external_api_clients.embedding_client import EmbeddingClient

from .formatting import format_rag_context
from .prompts import QUERY_EMBEDDING_INSTRUCTION
from .schemas import RagChunk, RAGContextResult


class RAGRetrievalService(LoggerMixin):
    def __init__(
        self,
        document_repo: RAGDocumentRepository,
        thread_repo: RAGThreadRepository,
        embedding_client: EmbeddingClient,
        top_k_documents: int = 5,
        top_k_threads: int = 5,
    ) -> None:
        if top_k_documents < 0 or top_k_threads < 0:
            raise ValueError("top_k must be non-negative")

        self._document_repo = document_repo
        self._thread_repo = thread_repo
        self._embedding_client = embedding_client
        self._top_k_documents = top_k_documents
        self._top_k_threads = top_k_threads

    async def get_context(
        self,
        query: str,
        top_k_docs: int | None = None,
        top_k_threads: int | None = None,
    ) -> RAGContextResult:
        """Получает релевантный контекст из базы знаний."""

        if not query.strip():
            raise ValueError("Query must not be empty")

        k_docs = (
            self._top_k_documents
            if top_k_docs is None
            else top_k_docs
        )
        k_threads = (
            self._top_k_threads
            if top_k_threads is None
            else top_k_threads
        )

        if k_docs < 0 or k_threads < 0:
            raise ValueError("top_k must be non-negative")

        if k_docs == 0 and k_threads == 0:
            return RAGContextResult()

        query_vector = await self._embedding_client.get_embedding(
            query,
            instruction=QUERY_EMBEDDING_INSTRUCTION,
        )

        document_results = (
            await self._document_repo.search(
                query_vector,
                top_k=k_docs,
            )
            if k_docs > 0
            else []
        )

        thread_results = (
            await self._thread_repo.search(
                query_vector,
                top_k=k_threads,
            )
            if k_threads > 0
            else []
        )

        documents = [
            self._document_to_chunk(item)
            for item in document_results
        ]
        threads = [
            self._thread_to_chunk(item)
            for item in thread_results
        ]

        self.logger.debug(
            "RAG search completed: documents=%d, threads=%d",
            len(documents),
            len(threads),
        )

        return RAGContextResult(
            documents=documents,
            threads=threads,
            formatted_context=format_rag_context(
                documents,
                threads,
            ),
            used_document_ids=list(
                dict.fromkeys(
                    doc.source_id for doc in documents
                )
            ),
            used_thread_ids=list(
                dict.fromkeys(
                    thread.source_id for thread in threads
                )
            ),
        )

    @staticmethod
    def _document_to_chunk(
        item: DocumentSearchResult,
    ) -> RagChunk:
        return RagChunk(
            id=str(item.id),
            source_type="company_doc",
            source_id=item.doc_id,
            content=(
                f"[{item.title}, Чанк {item.chunk_index}]\n"
                f"{item.content}"
            ),
            score=item.score,
        )

    @staticmethod
    def _thread_to_chunk(
        item: ThreadSearchResult,
    ) -> RagChunk:

        return RagChunk(
            id=str(item.id),
            source_type="thread_summary",
            source_id=str(item.thread_id),
            thread_id=str(item.thread_id),
            date=item.date,
            content=item.content,
            score=item.score,
        )
