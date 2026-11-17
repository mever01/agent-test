from unittest.mock import AsyncMock, MagicMock

from app.db.dao.rag.document_chunk import DocumentChunkDAO
from app.dto.rag import IndexedChunk


async def test_document_chunk_dao_search_empty():
    factory = MagicMock()
    dao = DocumentChunkDAO(session_factory=factory)

    result = await dao.search(query_vector=[0.1, 0.2], top_k=0)
    assert result == []
    factory.assert_not_called()


async def test_document_chunk_dao_replace_chunks():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.add_all = MagicMock()

    factory = MagicMock()
    factory.begin.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.begin.return_value.__aexit__ = AsyncMock(return_value=None)

    dao = DocumentChunkDAO(session_factory=factory)

    chunks = [
        IndexedChunk(1, "Чанк 1", [0.1, 0.2]),
        IndexedChunk(2, "Чанк 2", [0.3, 0.4]),
    ]

    await dao.replace_chunks(doc_id="doc_test", title="Тест", chunks=chunks)

    session.execute.assert_awaited_once()
    session.add_all.assert_called_once()
    added = session.add_all.call_args[0][0]
    assert len(added) == 2
    assert added[0].doc_id == "doc_test"
    assert added[1].chunk_index == 2
