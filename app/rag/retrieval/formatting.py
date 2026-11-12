
from collections.abc import Sequence

from .schemas import RagChunk


def format_rag_context(
    documents: Sequence[RagChunk],
    threads: Sequence[RagChunk],
) -> str:
    """Формирует текстовый контекст для LLM."""

    sections: list[str] = []

    if documents:
        document_text = "\n\n".join(
            f"--- ДОКУМЕНТ [{doc.source_id}] ---\n{doc.content}"
            for doc in documents
        )

        sections.append(
            "=== СПРАВОЧНЫЕ ДОКУМЕНТЫ КОМПАНИИ ===\n"
            + document_text
        )

    if threads:
        thread_text = "\n\n".join(
            f"--- АРХИВ ТРЕДА [{thread.source_id}] ---\n{thread.content}"
            for thread in threads
        )

        sections.append(
            "=== АРХИВ ПРОШЛЫХ ДОГОВОРЕННОСТЕЙ ===\n"
            + thread_text
        )

    return "\n\n".join(sections)
