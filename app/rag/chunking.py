import re

def split_markdown_by_headers_or_size(
    text: str,
    max_chunk_chars: int = 1500,
    overlap_chars: int = 200,
) -> list[str]:
    """
    Разбивает документ компании на логические чанки.
    Сначала пытается разбить по заголовкам markdown (# / ## / ###),
    если секция слишком большая — делит по абзацам с перекрытием.
    """
    # 1. Попытка разбить по заголовкам второго уровня ##
    sections = re.split(r"\n(?=##\s)", text)
    chunks = []

    for section in sections:
        section = section.strip()
        if not section:
            continue

        if len(section) <= max_chunk_chars:
            chunks.append(section)
        else:
            # Делим длинную секцию по абзацам с overlap
            paragraphs = section.split("\n\n")
            current_chunk = ""
            for p in paragraphs:
                p = p.strip()
                if not p:
                    continue
                if len(current_chunk) + len(p) + 2 <= max_chunk_chars:
                    current_chunk = f"{current_chunk}\n\n{p}".strip()
                else:
                    if current_chunk:
                        chunks.append(current_chunk)
                    # Начинаем новый чанк с перекрытием или с текущего абзаца
                    current_chunk = p
            if current_chunk:
                chunks.append(current_chunk)

    return chunks if chunks else [text]

