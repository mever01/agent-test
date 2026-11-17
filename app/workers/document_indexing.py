import asyncio
import logging
from contextlib import AsyncExitStack

from app.broker.rag.consumer import DocIngestConsumer
from app.broker.rag.topology import RAGTopology
from app.configs import settings
from app.db.dao.rag.document_chunk import DocumentChunkDAO
from app.db.session import AsyncSessionLocal, engine
from app.external_api_clients.embedding_client import EmbeddingClient
from app.services.rag.ingestion.document.service import DocumentIngestionService

from core.broker.client import RabbitMQClient


logger = logging.getLogger(__name__)


async def main() -> None:
    """Запускает обработчик очереди индексации документов компании."""
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    async with AsyncExitStack() as stack:
        stack.push_async_callback(engine.dispose)

        rabbit = await stack.enter_async_context(
            RabbitMQClient(settings.rabbitmq.url)
        )

        channel = await rabbit.get_channel()
        await channel.set_qos(prefetch_count=1)

        topology = RAGTopology(channel)
        resources = await topology.setup()

        embedding_client = EmbeddingClient()
        stack.push_async_callback(embedding_client.close)

        document_dao = DocumentChunkDAO(AsyncSessionLocal)
        ingestion_service = DocumentIngestionService(document_dao, embedding_client)
        document_consumer = DocIngestConsumer(
            queue=resources.queues.documents,
            ingestion_service=ingestion_service,
        )

        logger.info("Starting document indexing worker")
        await document_consumer.start()


if __name__ == "__main__":
    asyncio.run(main())
