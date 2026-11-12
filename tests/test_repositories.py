import uuid
from datetime import datetime, timezone
from app.db.schemas import IndexedDocumentChunk

from unittest.mock import AsyncMock, MagicMock
import pytest

from app.db.repositories.rag_document_repository import RAGDocumentRepository
from app.db.repositories.rag_thread_repository import RAGThreadRepository


async def test_rag_document_repository_search_empty():
    factory = MagicMock()
    repo = RAGDocumentRepository(session_factory=factory)

    result = await repo.search(query_vector=[0.1, 0.2], top_k=0)
    assert result == []
    factory.assert_not_called()


async def test_rag_document_repository_replace_chunks():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.add_all = MagicMock()

    factory = MagicMock()
    factory.begin.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.begin.return_value.__aexit__ = AsyncMock(return_value=None)

    repo = RAGDocumentRepository(session_factory=factory)

    chunks = [
        IndexedDocumentChunk(1, "Чанк 1", [0.1, 0.2]),
        IndexedDocumentChunk(2, "Чанк 2", [0.3, 0.4]),
    ]

    await repo.replace_chunks(doc_id="doc_test", title="Тест", chunks=chunks)

    session.execute.assert_awaited_once()
    session.add_all.assert_called_once()
    added = session.add_all.call_args[0][0]
    assert len(added) == 2
    assert added[0].doc_id == "doc_test"
    assert added[1].chunk_index == 2


async def test_rag_thread_repository_upsert():
    session = AsyncMock()
    mock_result = MagicMock()
    expected_id = uuid.uuid4()
    mock_result.scalar_one.return_value = expected_id
    session.execute = AsyncMock(return_value=mock_result)

    factory = MagicMock()
    factory.begin.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.begin.return_value.__aexit__ = AsyncMock(return_value=None)

    repo = RAGThreadRepository(session_factory=factory)

    test_thread = uuid.uuid4()
    vector_id = await repo.upsert(
        thread_id=test_thread,
        date=datetime.now(timezone.utc),
        content="Сводка переписки",
        embedding=[0.1, 0.2, 0.3],
    )

    assert vector_id == expected_id
    session.execute.assert_awaited_once()
