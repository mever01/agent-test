import re


def _normalize_text(text: str) -> str:
    """Нормализует переводы строк (включая CRLF) и концевые пробелы."""
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _split_sections(normalized_text: str) -> list[str]:
    """Разбивает текст по Markdown-заголовкам первого-третьего уровней."""
    sections = re.split(r"\n(?=#{1,3}\s)", normalized_text)
    return [s.strip() for s in sections if s.strip()]


def _extract_header(section: str) -> tuple[str, str]:
    """Извлекает заголовок секции (# / ## / ###) и возвращает (prefix, body)."""
    match = re.match(r"^(#{1,3}\s+[^\n]+)", section)
    if not match:
        return "", section.strip()
    header = match.group(1)
    body = section[len(header):].strip()
    return f"{header}\n\n", body


def _split_long_paragraph(
    paragraph: str,
    max_size: int,
    overlap: int,
) -> list[str]:
    """Нарезает сверхдлинный абзац скользящим окном с перекрытием."""
    effective_max = max(max_size, 50)
    step = max(effective_max - overlap, 20)
    if len(paragraph) <= effective_max:
        return [paragraph]
    return [
        paragraph[i : i + effective_max]
        for i in range(0, len(paragraph), step)
    ]


def _accumulate_part(
    chunks: list[str],
    current_chunk: str,
    header_prefix: str,
    part: str,
    max_chunk_chars: int,
    overlap_chars: int,
) -> str:
    """Добавляет фрагмент в текущий чанк либо фиксирует его и открывает новый с overlap."""
    candidate = (
        f"{current_chunk}\n\n{part}".strip()
        if current_chunk != header_prefix
        else f"{header_prefix}{part}".strip()
    )

    if len(candidate) <= max_chunk_chars:
        return candidate

    if current_chunk.strip() and current_chunk != header_prefix:
        chunks.append(current_chunk.strip())

    body = (
        current_chunk[len(header_prefix):].strip()
        if header_prefix
        else current_chunk.strip()
    )
    overlap = body[-overlap_chars:].strip() if overlap_chars > 0 else ""
    candidate_with_overlap = f"{header_prefix}{overlap}\n\n{part}".strip()

    if overlap and len(candidate_with_overlap) <= max_chunk_chars:
        return candidate_with_overlap
    return f"{header_prefix}{part}".strip()


def _chunk_section(
    section: str,
    max_chunk_chars: int,
    overlap_chars: int,
) -> list[str]:
    """Разбивает секцию на подчанки с сохранением заголовка и overlap."""
    header_prefix, body = _extract_header(section)
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]

    chunks: list[str] = []
    current_chunk = header_prefix
    max_body_size = max_chunk_chars - len(header_prefix)

    for p in paragraphs:
        parts = _split_long_paragraph(p, max_body_size, overlap_chars)
        for part in parts:
            current_chunk = _accumulate_part(
                chunks=chunks,
                current_chunk=current_chunk,
                header_prefix=header_prefix,
                part=part,
                max_chunk_chars=max_chunk_chars,
                overlap_chars=overlap_chars,
            )

    if current_chunk.strip() and current_chunk != header_prefix:
        chunks.append(current_chunk.strip())

    return chunks


def split_markdown_by_headers_or_size(
    text: str,
    max_chunk_chars: int = 1500,
    overlap_chars: int = 200,
) -> list[str]:
    """Разбивает Markdown-документ на смысловые чанки:

    1. Делит по заголовкам (# / ## / ###).
    2. При превышении max_chunk_chars делит секцию по абзацам с перекрытием (overlap_chars).
    3. Сохраняет заголовок секции в каждом подчанке для сохранения контекста RAG.
    """
    if max_chunk_chars <= 0:
        raise ValueError("max_chunk_chars must be positive")

    if not 0 <= overlap_chars < max_chunk_chars:
        raise ValueError("Invalid overlap_chars")

    if not text or not text.strip():
        return []

    normalized = _normalize_text(text)
    sections = _split_sections(normalized)
    chunks: list[str] = []

    for section in sections:
        if len(section) <= max_chunk_chars:
            chunks.append(section)
        else:
            chunks.extend(
                _chunk_section(
                    section=section,
                    max_chunk_chars=max_chunk_chars,
                    overlap_chars=overlap_chars,
                )
            )

    return chunks if chunks else [normalized]
