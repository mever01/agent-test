import asyncio
import json
import logging
import uuid
from pathlib import Path
from contextlib import AsyncExitStack
from datetime import datetime

from app.configs import settings
from app.db.session import init_db, AsyncSessionLocal, engine
from app.db.repositories.mail_repository import MailRepository
from app.db.repositories.rag_document_repository import RAGDocumentRepository
from app.db.repositories.rag_thread_repository import RAGThreadRepository
from app.external_api_clients.embedding_client import EmbeddingClient
from app.external_api_clients.llm_client import LLMClient
from app.db.repositories.user_repository import UserRepository
from app.rag.ingestion import RAGIngestionService
from app.services.auth_service import hash_password

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_data")

async def seed_base_user(users: UserRepository, email: str, password: str) -> None:
    email = email.strip().lower()
    if not email or "@" not in email:
        raise ValueError("SEED_USER_EMAIL должен содержать корректный email.")
    if await users.by_email(email) is None:
        digest = await asyncio.to_thread(hash_password, password)
        await users.add_seed_manager(email, digest)


async def seed() -> None:
    logger.info("Инициализация базы данных и таблиц...")
    await init_db()

    # Восстанавливаем уровень логирования INFO после alembic fileConfig
    logging.getLogger().setLevel(logging.INFO)
    logger.setLevel(logging.INFO)

    closed_threads: list[uuid.UUID] = []
    async with AsyncExitStack() as stack:
        stack.push_async_callback(engine.dispose)
        await seed_base_user(
            UserRepository(AsyncSessionLocal),
            settings.seed_user_email,
            settings.seed_user_password.get_secret_value(),
        )
        mail_repo = MailRepository(AsyncSessionLocal)
        embed_client = EmbeddingClient()
        llm_client = LLMClient()
        stack.push_async_callback(embed_client.close)
        stack.push_async_callback(llm_client.close)
        ingestion_service = RAGIngestionService(
            mail_repo, RAGDocumentRepository(AsyncSessionLocal),
            RAGThreadRepository(AsyncSessionLocal), embed_client, llm_client,
        )

        base_dir = Path(__file__).resolve().parents[1]

        # 1. Загрузка писем и тредов
        seed_file = base_dir / "data" / "seed_emails.json"
        logger.info("Проверка файла сида писем: %s (существует: %s)", seed_file, seed_file.exists())
        if seed_file.exists():
            logger.info("Загрузка учебных тредов и писем...")
            data = json.loads(await asyncio.to_thread(seed_file.read_text, encoding="utf-8"))

            for th in data.get("threads", []):
                thread_id = uuid.UUID(th["id"])
                await mail_repo.upsert_thread(
                    thread_id=thread_id,
                    subject=th["subject"],
                    client_email=th["client_email"],
                    status=th.get("status", "active"),
                )
                if th.get("status") == "closed":
                    closed_threads.append(thread_id)

            for em in data.get("emails", []):
                await mail_repo.insert_email(
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
        logger.info(
            "Проверка директории документов: %s (существует: %s)", docs_dir, docs_dir.exists(),
        )
        if docs_dir.exists():
            for doc_file in docs_dir.glob("*.md"):
                doc_id = doc_file.stem
                title = doc_file.stem.replace("_", " ").title()
                content = await asyncio.to_thread(doc_file.read_text, encoding="utf-8")
                logger.info("Индексация документа %s в RAG...", doc_id)
                await ingestion_service.process_document(
                    doc_id=doc_id, title=title, content=content,
                )

        for thread_id in closed_threads:
            await ingestion_service.ingest_thread(thread_id)

        logger.info("Первоначальный сидинг данных завершен!")

if __name__ == "__main__":
    asyncio.run(seed())

