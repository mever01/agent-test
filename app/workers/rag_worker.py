
import asyncio
import logging
from contextlib import AsyncExitStack

from core.broker.client import RabbitMQClient

from app.broker.rag.consumer import (
    DocIngestConsumer,
    ThreadClosedConsumer,
)
from app.broker.rag.topology import RAGTopology
from app.configs import settings
from app.db.repositories.mail_repository import MailRepository
from app.db.repositories.rag_document_repository import RAGDocumentRepository
from app.db.repositories.rag_thread_repository import RAGThreadRepository
from app.db.session import AsyncSessionLocal, engine
from app.external_api_clients.embedding_client import EmbeddingClient
from app.external_api_clients.llm_client import LLMClient
from app.rag.ingestion.service import RAGIngestionService


logger = logging.getLogger(__name__)


async def main() -> None:
    async with AsyncExitStack() as stack:
        # 1. SQLAlchemy
        stack.push_async_callback(engine.dispose)

        # 2. RabbitMQ
        rabbit = await stack.enter_async_context(
            RabbitMQClient(settings.rabbitmq.url)
        )

        channel = await rabbit.get_channel()
        await channel.set_qos(prefetch_count=1)

        # 3. RabbitMQ topology
        topology = RAGTopology(channel)
        resources = await topology.setup()

        # 4. External API clients
        embedding_client = EmbeddingClient()
        stack.push_async_callback(embedding_client.close)

        llm_client = LLMClient()
        stack.push_async_callback(llm_client.close)

        # 5. DB repositories
        mail_repo = MailRepository(AsyncSessionLocal)
        document_repo = RAGDocumentRepository(AsyncSessionLocal)
        thread_repo = RAGThreadRepository(AsyncSessionLocal)

        # 6. RAG ingestion service
        ingestion_service = RAGIngestionService(
            mail_repo=mail_repo,
            document_repo=document_repo,
            thread_repo=thread_repo,
            embedding_client=embedding_client,
            llm_client=llm_client,
        )

        # 7. RabbitMQ consumers
        thread_consumer = ThreadClosedConsumer(
            queue=resources.queues.threads,
            ingestion_service=ingestion_service,
        )

        document_consumer = DocIngestConsumer(
            queue=resources.queues.documents,
            ingestion_service=ingestion_service,
        )

        logger.info("Starting RAG worker")

        # 8. Run consumers concurrently
        async with asyncio.TaskGroup() as tg:
            tg.create_task(
                thread_consumer.start(),
                name="thread-closed-consumer",
            )
            tg.create_task(
                document_consumer.start(),
                name="document-ingest-consumer",
            )


if __name__ == "__main__":
    asyncio.run(main())
