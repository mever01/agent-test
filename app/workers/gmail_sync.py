import asyncio
import logging
from contextlib import AsyncExitStack
from datetime import timedelta

import httpx
from cryptography.fernet import Fernet
from sqlalchemy.exc import SQLAlchemyError

from app.configs import settings
from app.db.dao.gmail.gmail import GmailDAO
from app.db.session import AsyncSessionLocal, engine
from app.external_api_clients.gmail.client import GmailClient
from app.services.gmail.gmail_sync_service import GmailSyncService

logger = logging.getLogger(__name__)
_POLL_SECONDS = 5
_LEASE_DURATION = timedelta(minutes=2)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    gmail = settings.gmail
    if gmail.encryption_key is None:
        raise SystemExit("Set GMAIL_ENCRYPTION_KEY to run the Gmail worker.")
    cipher = Fernet(gmail.encryption_key.get_secret_value().encode())

    async with AsyncExitStack() as stack:
        stack.push_async_callback(engine.dispose)
        http = await stack.enter_async_context(httpx.AsyncClient(timeout=15))
        service = GmailSyncService(
            GmailDAO(AsyncSessionLocal),
            GmailClient(http),
            cipher,
            timedelta(seconds=gmail.sync_interval_seconds),
            lease_duration=_LEASE_DURATION,
        )
        logger.info("Gmail worker started")
        while True:
            try:
                if await service.run_next():
                    continue
            except SQLAlchemyError as exc:
                logger.error("Gmail worker database error type=%s", type(exc).__name__)
            await asyncio.sleep(_POLL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
