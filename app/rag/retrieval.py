from pydantic import BaseModel, Field
from app.db.repositories.vector_repository import VectorRepository
from app.external_api_clients.embedding_client import EmbeddingClient
from app.schemas.rag import RagChunk
from app.configs import settings

class RAGContextResult(BaseModel):
    documents: list[RagChunk] = Field(default_factory=list)
    threads: list[RagChunk] = Field(default_factory=list)
    formatted_context: str = ""
    used_document_ids: list[str] = Field(default_factory=list)
    used_thread_ids: list[str] = Field(default_factory=list)

class RAGRetrievalService:
    def __init__(
        self,
        vector_repo: VectorRepository,
        embedding_client: EmbeddingClient,
    ):
        self.repo = vector_repo
        self.embed = embedding_client

    async def get_context(
        self,
        query: str,
        top_k_docs: int | None = None,
        top_k_threads: int | None = None,
    ) -> RAGContextResult:
        """
        Параллельный семантический поиск по регламентам компании и архиву прошлых тредов.
        Использует instruction-aware эмбеддинги Qwen3.
        """
        k_docs = top_k_docs or settings.agent.top_k_documents
        k_threads = top_k_threads or settings.agent.top_k_threads

        instruction = "Given a user email inquiry, retrieve relevant company delivery rules and past client agreements"
        query_vector = await self.embed.get_embedding(query, instruction=instruction)

        # Поиск по двум изолированным коллекциям
        docs = await self.repo.search_documents(query_vector, top_k=k_docs)
        threads = await self.repo.search_threads(query_vector, top_k=k_threads)

        # Сборка форматированного блока для промпта
        doc_texts = []
        doc_ids = []
        for d in docs:
            doc_texts.append(f"--- ДОКУМЕНТ [{d.source_id}] ---\n{d.content}")
            if d.source_id not in doc_ids:
                doc_ids.append(d.source_id)

        thread_texts = []
        thread_ids = []
        for t in threads:
            thread_texts.append(f"--- АРХИВ ТРЕДА [{t.source_id}] ---\n{t.content}")
            if t.source_id not in thread_ids:
                thread_ids.append(t.source_id)

        formatted_context = ""
        if doc_texts:
            formatted_context += "\n=== СПРАВОЧНЫЕ ДОКУМЕНТЫ КОМПАНИИ ===\n" + "\n\n".join(doc_texts)
        if thread_texts:
            formatted_context += "\n\n=== АРХИВ ПРОШЛЫХ ДОГОВОРЕННОСТЕЙ ===\n" + "\n\n".join(thread_texts)

        return RAGContextResult(
            documents=docs,
            threads=threads,
            formatted_context=formatted_context.strip(),
            used_document_ids=doc_ids,
            used_thread_ids=thread_ids,
        )

