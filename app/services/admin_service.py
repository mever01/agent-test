import asyncio
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from app.guardrails.schemas import SecurityEventLog
from core.utils.mixins.logger import LoggerMixin
from app.broker.rag.constants import Queue
from app.broker.rag.producer import RAGProducer
from app.configs import settings
from app.services.exceptions import (
    DocumentAccessDeniedError,
    DocumentNotFoundError,
)


@dataclass(frozen=True, slots=True)
class DocumentQueued:
    status: str
    doc_id: str
    title: str
    queue: str


class AdminService(LoggerMixin):
    def __init__(
        self,
        rag_producer: RAGProducer,
        allowed_dir: Path | None = None,
    ) -> None:
        self._rag_producer = rag_producer
        self._allowed_dir = allowed_dir or Path('data/documents')

    async def ingest_document(
        self,
        doc_id: str,
        title: str,
        file_path: str | Path,
    ) -> DocumentQueued:
        """Проверяет безопасность пути файла и публикует задание на индексацию."""
        resolved_path = await asyncio.to_thread(_resolve_document, file_path, self._allowed_dir)

        await self._rag_producer.publish_doc_ingest(
            doc_id=doc_id,
            title=title,
            file_path=resolved_path,
        )

        return DocumentQueued("queued", doc_id, title, Queue.DOCUMENTS)

    async def get_security_events(
        self,
        limit: int = 50,
        log_path: Path | None = None,
    ) -> list[SecurityEventLog]:
        path = log_path or settings.guardrails.security_log_path
        return await asyncio.to_thread(read_security_events, path, limit)


def _resolve_document(file_path: str | Path, allowed_dir: Path) -> Path:
    path = Path(file_path).resolve()
    if not path.is_relative_to(allowed_dir.resolve()):
        raise DocumentAccessDeniedError(
            f"Доступ к файлу {file_path} запрещен политикой безопасности."
        )
    if not path.is_file():
        raise DocumentNotFoundError(f"Файл {file_path} не существует на сервере.")
    return path


def read_security_events(path: Path, limit: int) -> list[SecurityEventLog]:
    events: deque[SecurityEventLog] = deque(maxlen=limit)
    try:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    events.append(SecurityEventLog.model_validate_json(line))
                except ValidationError:
                    continue
    except FileNotFoundError:
        return []
    return list(events)
