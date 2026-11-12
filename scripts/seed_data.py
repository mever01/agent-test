import asyncio
import json
import logging
import uuid
from pathlib import Path
from datetime import datetime

from app.db.session import init_db, AsyncSessionLocal
from app.db.repositories.email_repository import EmailRepository
from app.db.repositories.vector_repository import VectorRepository
from app.external_api_clients.embedding_client import EmbeddingClient
from app.external_api_clients.llm_client import LLMClient
from app.rag.ingestion import RAGIngestionService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_data")

async def seed():
    logger.info("Инициализация базы данных и таблиц...")
    await init_db()

    # Восстанавливаем уровень логирования INFO после alembic fileConfig
    logging.getLogger().setLevel(logging.INFO)
    logger.setLevel(logging.INFO)

    async with AsyncSessionLocal() as session:
        email_repo = EmailRepository(session)
        vector_repo = VectorRepository(session)
        embed_client = EmbeddingClient()
        llm_client = LLMClient()
        ingestion_service = RAGIngestionService(vector_repo, embed_client, llm_client)

        base_dir = Path(__file__).resolve().parents[1]

        # 1. Загрузка писем и тредов
        seed_file = base_dir / "data" / "seed_emails.json"
        logger.info(f"Проверка файла сида писем: {seed_file} (существует: {seed_file.exists()})")
        if seed_file.exists():
            logger.info("Загрузка учебных тредов и писем...")
            data = json.loads(seed_file.read_text(encoding="utf-8"))

            for th in data.get("threads", []):
                await email_repo.upsert_thread(
                    thread_id=uuid.UUID(th["id"]),
                    subject=th["subject"],
                    client_email=th["client_email"],
                    status=th.get("status", "active"),
                )

            for em in data.get("emails", []):
                await email_repo.insert_email(
                    email_id=uuid.UUID(em["id"]),
                    thread_id=uuid.UUID(em["thread_id"]),
                    sender=em["sender"],
                    recipient=em["recipient"],
                    date=datetime.fromisoformat(em["date"].replace("Z", "+00:00")),
                    subject=em["subject"],
                    body=em["body"],
                )
            logger.info("Учебные письма и треды успешно добавлены.")

        # 2. Загрузка справочных документов компании
        docs_dir = base_dir / "data" / "documents"
        logger.info(f"Проверка директории документов: {docs_dir} (существует: {docs_dir.exists()})")
        if docs_dir.exists():
            for doc_file in docs_dir.glob("*.md"):
                doc_id = doc_file.stem
                title = doc_file.stem.replace("_", " ").title()
                content = doc_file.read_text(encoding="utf-8")
                logger.info(f"Индексация документа {doc_id} в RAG...")
                try:
                    await ingestion_service.process_document(doc_id=doc_id, title=title, content=content)
                except Exception as e:
                    logger.warning(f"Не удалось векторизовать документ {doc_id} (проверьте запуск embedder): {e}")

        logger.info("Первоначальный сидинг данных завершен!")

if __name__ == "__main__":
    asyncio.run(seed())

