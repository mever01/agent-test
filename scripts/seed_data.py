import asyncio
from contextlib import AsyncExitStack
from datetime import datetime
import json
import logging
from pathlib import Path
import uuid

from sqlalchemy.dialects.postgresql import insert

from app.configs import settings
from app.db.dao.db_mail.raw_email import RawEmailDAO
from app.db.dao.db_mail.thread import ThreadDAO
from app.db.dao.rag.document_chunk import DocumentChunkDAO
from app.db.dao.user import UserRepository
from app.db.enums import AccountSource
from app.db.models import GmailAccount
from app.db.session import init_db, AsyncSessionLocal, engine
from app.dto.db_mail import EmailWrite, ThreadWrite
from app.dto.rag import DocumentContent
from app.external_api_clients.embedding_client import EmbeddingClient
from app.services.auth_service import hash_password
from app.services.rag.ingestion.document.service import DocumentIngestionService

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

    async with AsyncExitStack() as stack:
        stack.push_async_callback(engine.dispose)
        users = UserRepository(AsyncSessionLocal)
        await seed_base_user(
            users,
            settings.seed_user_email,
            settings.seed_user_password.get_secret_value(),
        )
        threads = ThreadDAO(AsyncSessionLocal)
        emails = RawEmailDAO(AsyncSessionLocal)
        embed_client = EmbeddingClient()
        stack.push_async_callback(embed_client.close)
        ingestion_service = DocumentIngestionService(
            DocumentChunkDAO(AsyncSessionLocal), embed_client,
        )

        base_dir = Path(__file__).resolve().parents[1]

        # 1. Загрузка писем и тредов
        seed_file = base_dir / "data" / "seed_emails.json"
        logger.info("Проверка файла сида писем: %s (существует: %s)", seed_file, seed_file.exists())
        if seed_file.exists():
            logger.info("Загрузка учебных тредов и писем...")
            data = json.loads(await asyncio.to_thread(seed_file.read_text, encoding="utf-8"))
            owner = await users.by_email(settings.seed_user_email.strip().lower())
            if owner is None:
                raise RuntimeError("Не найден владелец учебных писем.")
            account_id = uuid.uuid5(owner.id, "seed-gmail")
            async with AsyncSessionLocal.begin() as session:
                await session.execute(
                    insert(GmailAccount)
                    .values(id=account_id, owner_id=owner.id, name="Учебная почта")
                    .on_conflict_do_nothing(index_elements=[GmailAccount.id]),
                )

            for th in data.get("threads", []):
                thread_id = uuid.uuid5(account_id, th["id"])
                await threads.upsert_thread(ThreadWrite(
                    thread_id=thread_id,
                    subject=th["subject"],
                    client_email=th["client_email"],
                    account_source=AccountSource.GMAIL,
                    account_id=account_id,
                    external_thread_id=th["id"],
                ))

            for em in data.get("emails", []):
                await emails.insert_email(EmailWrite(
                    email_id=uuid.uuid5(account_id, em["id"]),
                    thread_id=uuid.uuid5(account_id, em["thread_id"]),
                    sender=em["sender"],
                    recipient=em["recipient"],
                    date=datetime.fromisoformat(em["date"].replace("Z", "+00:00")),
                    subject=em["subject"],
                    body=em["body"],
                    account_source=AccountSource.GMAIL,
                    account_id=account_id,
                    message_id=em["id"],
                ))
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
                await ingestion_service.process_document(DocumentContent(
                    doc_id, title, content,
                ))

        logger.info("Первоначальный сидинг данных завершен!")

if __name__ == "__main__":
    asyncio.run(seed())
