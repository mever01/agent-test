from app.services.rag.ingestion.chunking import split_markdown_by_headers_or_size
from app.services.rag.ingestion.email.text_cleaner import clean_email_body

BODY_CHUNK_CHARS = 1100
OVERLAP_CHARS = 200
SUBJECT_CHARS = 300


def prepare_email_fragments(subject: str, body: str) -> list[str]:
    """Очищает письмо и добавляет тему к каждому ограниченному по длине фрагменту."""
    cleaned = clean_email_body(body, keep_forwarded=True)
    prefix = subject.strip()[:SUBJECT_CHARS]
    sections = split_markdown_by_headers_or_size(
        cleaned, max_chunk_chars=BODY_CHUNK_CHARS, overlap_chars=OVERLAP_CHARS,
    )
    fragments: list[str] = []
    for section in sections:
        if len(section) <= BODY_CHUNK_CHARS:
            fragments.append(section)
        else:
            fragments.extend(
                section[offset : offset + BODY_CHUNK_CHARS]
                for offset in range(0, len(section), BODY_CHUNK_CHARS - OVERLAP_CHARS)
            )
    prepared = [f"{prefix}\n\n{part}".strip() for part in fragments]
    return prepared or ([prefix] if prefix else [])
