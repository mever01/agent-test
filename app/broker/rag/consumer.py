
from aio_pika.abc import AbstractQueue

from core.broker.consumer import RabbitConsumer
from app.dto.rag import DocumentFile
from app.services.rag.ingestion.document.service import DocumentIngestionService

from .schemas import DocIngestEvent


class DocIngestConsumer(RabbitConsumer[DocIngestEvent]):
    message_type = DocIngestEvent

    def __init__(
        self,
        queue: AbstractQueue,
        ingestion_service: DocumentIngestionService,
    ) -> None:
        super().__init__(queue)
        self._ingestion_service = ingestion_service

    async def handle(self, message: DocIngestEvent) -> None:
        self.logger.info(
            "Processing document: doc_id=%s, event_id=%s",
            message.doc_id,
            message.event_id,
        )

        chunks_count = await self._ingestion_service.ingest_document(DocumentFile(
            message.doc_id, message.title, message.file_path,
        ))

        self.logger.info(
            "Document processed: doc_id=%s, chunks=%d",
            message.doc_id,
            chunks_count,
        )
