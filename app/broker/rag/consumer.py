
from aio_pika.abc import AbstractQueue

from core.broker.consumer import RabbitConsumer
from app.rag.ingestion.service import RAGIngestionService

from .schemas import DocIngestEvent, ThreadClosedEvent


class ThreadClosedConsumer(RabbitConsumer[ThreadClosedEvent]):
    message_type = ThreadClosedEvent

    def __init__(
        self,
        queue: AbstractQueue,
        ingestion_service: RAGIngestionService,
    ) -> None:
        super().__init__(queue)
        self._ingestion_service = ingestion_service

    async def handle(self, message: ThreadClosedEvent) -> None:
        self.logger.info(
            "Processing thread: thread_id=%s, event_id=%s",
            message.thread_id,
            message.event_id,
        )

        success = await self._ingestion_service.ingest_thread(
            thread_id=message.thread_id,
        )

        if not success:
            self.logger.warning(
                "Thread is empty, skipping: thread_id=%s",
                message.thread_id,
            )
            return

        self.logger.info(
            "Thread processed: thread_id=%s",
            message.thread_id,
        )


class DocIngestConsumer(RabbitConsumer[DocIngestEvent]):
    message_type = DocIngestEvent

    def __init__(
        self,
        queue: AbstractQueue,
        ingestion_service: RAGIngestionService,
    ) -> None:
        super().__init__(queue)
        self._ingestion_service = ingestion_service

    async def handle(self, message: DocIngestEvent) -> None:
        self.logger.info(
            "Processing document: doc_id=%s, event_id=%s",
            message.doc_id,
            message.event_id,
        )

        chunks_count = await self._ingestion_service.ingest_document(
            doc_id=message.doc_id,
            title=message.title,
            file_path=message.file_path,
        )

        self.logger.info(
            "Document processed: doc_id=%s, chunks=%d",
            message.doc_id,
            chunks_count,
        )
