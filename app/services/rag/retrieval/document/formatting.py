from collections.abc import Sequence

from app.dto.rag import DocumentSearchResult, RagChunk


def document_to_chunk(item: DocumentSearchResult) -> RagChunk:
    """Добавляет к фрагменту название документа и номер источника."""
    return RagChunk(
        id=str(item.id), source_id=item.doc_id,
        content=f"[{item.title}, Чанк {item.chunk_index}]\n{item.content}",
        score=item.score,
    )


def format_document_context(documents: Sequence[RagChunk]) -> str:
    """Собирает контекст только из найденных документов компании."""
    if not documents:
        return ""
    body = "\n\n".join(
        f"--- ДОКУМЕНТ [{doc.source_id}] ---\n{doc.content}" for doc in documents
    )
    return f"=== СПРАВОЧНЫЕ ДОКУМЕНТЫ КОМПАНИИ ===\n{body}"
