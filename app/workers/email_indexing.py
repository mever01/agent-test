import asyncio
import logging
from contextlib import AsyncExitStack
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy.exc import SQLAlchemyError

from app.configs import settings
from app.configs.rag_worker import RagWorkerConfig
from app.db.dao.rag.email_chunk import EmailChunkDAO
from app.db.session import AsyncSessionLocal, engine
from app.external_api_clients.embedding_client import EmbeddingClient
from app.services.rag.ingestion.email.service import EmailIngestionService

logger = logging.getLogger(__name__)


async def index_pending_emails(
    email_dao: EmailChunkDAO,
    service: EmailIngestionService,
    config: RagWorkerConfig,
) -> None:
    """Периодически выбирает готовые письма и передаёт их сервису индексации."""
    delay = timedelta(minutes=config.indexing_delay_minutes)
    while True:
        try:
            jobs = await email_dao.pending_jobs(datetime.now(UTC) - delay)
            for job in jobs:
                try:
                    if await service.process_email(job):
                        logger.info("Email indexed email_id=%s", job.email_id)
                except (httpx.HTTPError, SQLAlchemyError, ValueError) as exc:
                    logger.warning(
                        "Email indexing failed email_id=%s type=%s",
                        job.email_id, type(exc).__name__,
                    )
        except SQLAlchemyError as exc:
            logger.warning("Email indexing database error type=%s", type(exc).__name__)
        await asyncio.sleep(60)


async def main() -> None:
    """Запускает периодическую индексацию писем с собственными ресурсами."""
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    async with AsyncExitStack() as stack:
        stack.push_async_callback(engine.dispose)
        embedding_client = EmbeddingClient()
        stack.push_async_callback(embedding_client.close)
        email_dao = EmailChunkDAO(AsyncSessionLocal)
        ingestion_service = EmailIngestionService(email_dao, embedding_client)
        logger.info(
            "Starting email indexing worker indexing_delay_minutes=%s",
            settings.rag_worker.indexing_delay_minutes,
        )
        await index_pending_emails(email_dao, ingestion_service, settings.rag_worker)


if __name__ == "__main__":
    asyncio.run(main())
