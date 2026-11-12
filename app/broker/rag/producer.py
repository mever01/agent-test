from pathlib import Path
from uuid import UUID

from core.broker.producer import RabbitProducer

from .constants import RoutingKey
from .schemas import ThreadClosedEvent, DocIngestEvent


class RAGProducer(RabbitProducer):
    async def publish_thread_closed(
        self,
        thread_id: UUID | str,
    ) -> None:
        event = ThreadClosedEvent(
            thread_id=UUID(str(thread_id)),
        )

        await self.publish(
            routing_key=RoutingKey.THREAD_CLOSED,
            payload=event,
        )

    async def publish_doc_ingest(
        self,
        doc_id: str,
        title: str,
        file_path: Path | str,
    ) -> None:
        event = DocIngestEvent(
            doc_id=doc_id,
            title=title,
            file_path=Path(file_path),
        )

        await self.publish(
            routing_key=RoutingKey.DOC_UPLOADED,
            payload=event,
        )