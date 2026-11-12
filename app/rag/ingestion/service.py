
import asyncio
from pathlib import Path
from uuid import UUID

from core.utils.mixins.logger import LoggerMixin

from app.db.repositories.mail_repository import MailRepository
from app.db.repositories.rag_document_repository import RAGDocumentRepository
from app.db.repositories.rag_thread_repository import RAGThreadRepository
from app.db.schemas import IndexedDocumentChunk, MailMessage
from app.external_api_clients.embedding_client import EmbeddingClient
from app.external_api_clients.llm_client import LLMClient

from .chunking import split_markdown_by_headers_or_size
from .prompts import THREAD_SUMMARY_SYSTEM_PROMPT
from .text_cleaner import format_cleaned_thread


class RAGIngestionService(LoggerMixin):
    def __init__(
        self,
        mail_repo: MailRepository,
        document_repo: RAGDocumentRepository,
        thread_repo: RAGThreadRepository,
        embedding_client: EmbeddingClient,
        llm_client: LLMClient,
    ) -> None:
        self._mail_repo = mail_repo
        self._document_repo = document_repo
        self._thread_repo = thread_repo
        self._embedding_client = embedding_client
        self._llm_client = llm_client

    async def ingest_thread(
        self,
        thread_id: UUID,
    ) -> bool:
        messages = await self._mail_repo.get_thread_emails(
            thread_id
        )

        if not messages:
            self.logger.warning(
                "Thread is empty: thread_id=%s",
                thread_id,
            )
            return False

        await self.process_thread(thread_id, messages)
        return True

    async def ingest_document(
        self,
        doc_id: str,
        title: str,
        file_path: Path,
    ) -> int:
        content = await asyncio.to_thread(
            file_path.read_text,
            encoding="utf-8",
        )

        return await self.process_document(
            doc_id=doc_id,
            title=title,
            content=content,
        )

    async def process_thread(
        self,
        thread_id: UUID,
        messages: list[MailMessage],
    ) -> UUID:
        if not messages:
            raise ValueError(
                f"Thread {thread_id} has no messages"
            )

        cleaned_text = format_cleaned_thread(messages)

        if not cleaned_text.strip():
            raise ValueError(
                f"Thread {thread_id} has no content after cleaning"
            )

        last_date = max(message.date for message in messages)

        response = await self._llm_client.chat(
            messages=[
                {
                    "role": "system",
                    "content": THREAD_SUMMARY_SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": (
                        "<untrusted_emails>\n"
                        f"{cleaned_text}\n"
                        "</untrusted_emails>"
                    ),
                },
            ],
        )

        summary = (response.content or "").strip()

        if not summary:
            raise ValueError(
                f"Empty LLM summary for thread {thread_id}"
            )

        embedding = await self._embedding_client.get_embedding(
            summary
        )

        # Репозиторий выполняет upsert и commit в атомарной транзакции
        vector_id = await self._thread_repo.upsert(
            thread_id=thread_id,
            date=last_date,
            content=summary,
            embedding=embedding,
        )

        self.logger.info(
            "Thread indexed: thread_id=%s, vector_id=%s",
            thread_id,
            vector_id,
        )

        return vector_id

    async def process_document(
        self,
        doc_id: str,
        title: str,
        content: str,
    ) -> int:
        chunks = split_markdown_by_headers_or_size(content)

        if not chunks:
            raise ValueError(
                f"Document {doc_id} has no content to index"
            )

        chunks_data: list[IndexedDocumentChunk] = []

        for index, chunk in enumerate(chunks, start=1):
            embedding = await self._embedding_client.get_embedding(
                chunk
            )
            chunks_data.append(IndexedDocumentChunk(index, chunk, embedding))

        # Репозиторий атомарно заменяет чанки (delete + insert) и коммитит транзакцию
        await self._document_repo.replace_chunks(
            doc_id=doc_id,
            title=title,
            chunks=chunks_data,
        )

        self.logger.info(
            "Document indexed: doc_id=%s, chunks=%d",
            doc_id,
            len(chunks_data),
        )

        return len(chunks_data)
