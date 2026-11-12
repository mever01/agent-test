import json
import logging
import aio_pika
from app.configs import settings
from app.queue.schemas import ThreadClosedEvent, DocIngestEvent

logger = logging.getLogger(__name__)

class EventPublisher:
    def __init__(self, rabbitmq_url: str | None = None):
        self.url = rabbitmq_url or settings.rabbitmq.url
        self.exchange_name = settings.rabbitmq.exchange
        self.threads_queue = settings.rabbitmq.threads_queue
        self.documents_queue = settings.rabbitmq.documents_queue

    async def publish_thread_closed(self, thread_id: str) -> None:
        """Публикует событие закрытия треда в rag.threads.queue."""
        event = ThreadClosedEvent(thread_id=thread_id)
        await self._publish(
            routing_key="rag.thread.closed",
            payload=event.model_dump(),
        )
        logger.info(f"Событие закрытия треда {thread_id} отправлено в очередь.")

    async def publish_doc_ingest(self, doc_id: str, title: str, file_path: str) -> None:
        """Публикует событие загрузки документа в rag.documents.queue."""
        event = DocIngestEvent(doc_id=doc_id, title=title, file_path=file_path)
        await self._publish(
            routing_key="rag.doc.uploaded",
            payload=event.model_dump(),
        )
        logger.info(f"Событие загрузки документа {doc_id} отправлено в очередь.")

    async def _publish(self, routing_key: str, payload: dict) -> None:
        try:
            connection = await aio_pika.connect_robust(self.url)
            async with connection:
                channel = await connection.channel()
                
                # Объявляем topic exchange
                exchange = await channel.declare_exchange(
                    self.exchange_name,
                    aio_pika.ExchangeType.TOPIC,
                    durable=True,
                )

                # Гарантируем объявление очередей
                threads_q = await channel.declare_queue(self.threads_queue, durable=True)
                docs_q = await channel.declare_queue(self.documents_queue, durable=True)

                await threads_q.bind(exchange, "rag.thread.*")
                await docs_q.bind(exchange, "rag.doc.*")

                # Отправляем сообщение
                message = aio_pika.Message(
                    body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    content_type="application/json",
                )
                await exchange.publish(message, routing_key=routing_key)
        except Exception as e:
            logger.error(f"Не удалось отправить событие в RabbitMQ ({self.url}): {e}")
            raise e

