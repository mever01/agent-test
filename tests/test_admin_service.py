from pathlib import Path
from unittest.mock import AsyncMock
import pytest

from app.services.admin_service import AdminService
from app.services.exceptions import (
    DocumentAccessDeniedError,
    DocumentNotFoundError,
)


async def test_admin_service_ingest_document_success(tmp_path: Path):
    doc_file = tmp_path / "policy.md"
    doc_file.write_text("# Регламент\nТекст регламента.", encoding="utf-8")

    publisher = AsyncMock()
    service = AdminService(rag_producer=publisher, allowed_dir=tmp_path)

    result = await service.ingest_document(
        doc_id="doc_1",
        title="Политика безопасности",
        file_path=str(doc_file),
    )

    assert result.status == "queued"
    assert result.doc_id == "doc_1"
    assert result.queue == "rag.documents.queue"
    publisher.publish_doc_ingest.assert_awaited_once_with(
        doc_id="doc_1",
        title="Политика безопасности",
        file_path=doc_file.resolve(),
    )


async def test_admin_service_ingest_document_not_found(tmp_path: Path):
    publisher = AsyncMock()
    service = AdminService(rag_producer=publisher, allowed_dir=tmp_path)

    with pytest.raises(DocumentNotFoundError):
        await service.ingest_document(
            doc_id="doc_2",
            title="Нет файла",
            file_path=str(tmp_path / "non_existent.md"),
        )


async def test_admin_service_directory_traversal_blocked(tmp_path: Path):
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()

    outside_dir = tmp_path / "secret"
    outside_dir.mkdir()
    secret_file = outside_dir / "passwords.txt"
    secret_file.write_text("secret", encoding="utf-8")

    publisher = AsyncMock()
    service = AdminService(rag_producer=publisher, allowed_dir=allowed_dir)

    with pytest.raises(DocumentAccessDeniedError):
        await service.ingest_document(
            doc_id="hack_1",
            title="Взлом",
            file_path=str(secret_file),
        )


async def test_admin_service_get_security_events(tmp_path: Path):
    log_file = tmp_path / "security_events.jsonl"
    log_file.write_text(
        '{"timestamp": "2026-11-15T00:00:00Z", "location": "model_response", "run_id": "r1", "reason": "CANARY_MATCH", "action": "BLOCKED"}\n'
        '{"timestamp": "2026-11-15T00:00:00Z", "location": "model_response", "run_id": "r2", "reason": "CANARY_MATCH", "action": "BLOCKED"}\n',
        encoding="utf-8",
    )

    publisher = AsyncMock()
    service = AdminService(rag_producer=publisher, allowed_dir=tmp_path)

    events = await service.get_security_events(limit=1, log_path=log_file)
    assert len(events) == 1
    assert events[0].run_id == "r2"
