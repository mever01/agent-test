import asyncio
import json
import logging
import uuid
from pathlib import Path
import aio_pika
from sqlalchemy.ext.asyncio import AsyncSession

from app.configs import settings
from app.db.session import AsyncSessionLocal
from app.db.repositories.email_repository import EmailRepository
from app.db.repositories.vector_repository import VectorRepository
from app.external_api_clients.embedding_client import EmbeddingClient
from app.external_api_clients.llm_client import LLMClient
from app.rag.ingestion import RAGIngestionService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("rag_worker")

async def process_thread_message(body: dict, session: AsyncSession, ingestion_service: RAGIngestionService) -> None:
    thread_id = body.get("thread_id")
    if not thread_id:
        logger.warning(f"Пропущено сообщение без thread_id: {body}")
        return

    email_repo = EmailRepository(session)
    try:
        th_uuid = uuid.UUID(thread_id)
    except Exception as e:
        logger.error(f"Некорректный UUID thread_id в сообщении: {thread_id} ({e})")
        return

    messages = await email_repo.get_thread_emails(th_uuid)
    if not messages:
        logger.warning(f"Для треда {thread_id} не найдены письма в БД.")
        return

    logger.info(f"Начало сжатия и векторизации треда {thread_id} ({len(messages)} писем)...")
    await ingestion_service.process_thread(thread_id, messages)

async def process_document_message(body: dict, session: AsyncSession, ingestion_service: RAGIngestionService) -> None:
    doc_id = body.get("doc_id")
    title = body.get("title")
    file_path = body.get("file_path")

    if not doc_id or not file_path:
        logger.warning(f"Пропущено сообщение документа с неполными данными: {body}")
        return

    path = Path(file_path)
    if not path.exists():
        logger.error(f"Файл документа {file_path} не найден на диске!")
        return

    content = path.read_text(encoding="utf-8")
    logger.info(f"Начало нарезки и векторизации документа {doc_id} ('{title}')...")
    await ingestion_service.process_document(doc_id=doc_id, title=title, content=content)

async def main() -> None:
    logger.info("Запуск RAG Worker процесса...")

    # Цикл повторных попыток подключения к RabbitMQ при холодном старте
    connection = None
    for attempt in range(1, 21):
        try:
            logger.info(f"Попытка подключения к RabbitMQ ({attempt}/20) по адресу {settings.rabbitmq.url}...")
            connection = await aio_pika.connect_robust(settings.rabbitmq.url)
            logger.info("Успешное подключение к RabbitMQ!")
            break
        except Exception as e:
            logger.warning(f"RabbitMQ еще не готов принимать соединения ({e}). Повтор через 2 сек...")
            await asyncio.sleep(2)

    if not connection:
        logger.error("Критическая ошибка: не удалось подключиться к RabbitMQ после 20 попыток!")
        return

    embed_client = EmbeddingClient()
    llm_client = LLMClient()

    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=2)

        exchange = await channel.declare_exchange(
            settings.rabbitmq.exchange,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )

        threads_q = await channel.declare_queue(
            settings.rabbitmq.threads_queue,
            durable=True,
            arguments={
                "x-dead-letter-exchange": f"{settings.rabbitmq.exchange}.dlx",
                "x-dead-letter-routing-key": "rag.dead",
            },
        )
        docs_q = await channel.declare_queue(
            settings.rabbitmq.documents_queue,
            durable=True,
            arguments={
                "x-dead-letter-exchange": f"{settings.rabbitmq.exchange}.dlx",
                "x-dead-letter-routing-key": "rag.dead",
            },
        )

        # DLX / DLQ: отдельный exchange и очередь для невалидных / необрабатываемых сообщений
        dlx = await channel.declare_exchange(
            f"{settings.rabbitmq.exchange}.dlx",
            aio_pika.ExchangeType.DIRECT,
            durable=True,
        )
        dlq = await channel.declare_queue("rag.dead.queue", durable=True)
        await dlq.bind(dlx, "rag.dead")

        await threads_q.bind(exchange, "rag.thread.*")
        await docs_q.bind(exchange, "rag.doc.*")

        logger.info("Подписка на очереди rag.threads.queue и rag.documents.queue оформлена.")

        async def on_message(message: aio_pika.IncomingMessage) -> None:
            try:
                payload = json.loads(message.body.decode("utf-8"))
                event_type = payload.get("event_type")
                logger.info(f"Получено событие: {event_type} (id={payload.get('event_id')})")

                async with AsyncSessionLocal() as session:
                    vector_repo = VectorRepository(session)
                    ingestion_service = RAGIngestionService(
                        vector_repo=vector_repo,
                        embedding_client=embed_client,
                        llm_client=llm_client,
                    )

                    if event_type == "THREAD_CLOSED":
                        await process_thread_message(payload, session, ingestion_service)
                    elif event_type == "DOC_INGEST":
                        await process_document_message(payload, session, ingestion_service)
                    else:
                        logger.warning(f"Неизвестный тип события: {event_type}")

                await message.ack()

            except Exception as e:
                logger.error(f"Ошибка при обработке сообщения — отправляем в DLQ: {e}", exc_info=True)
                await message.nack(requeue=False)

        await threads_q.consume(on_message)
        await docs_q.consume(on_message)

        # Бесконечный цикл ожидания
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())

