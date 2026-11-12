from app.rag.ingestion.chunking import split_markdown_by_headers_or_size


def test_split_markdown_by_headers():
    doc = """# Главный заголовок

## Раздел 1. Условия отгрузки
Отгрузка осуществляется за 10 дней со склада.

## Раздел 2. Условия оплаты
Предоплата 50% в течение 3 дней.
"""
    chunks = split_markdown_by_headers_or_size(doc, max_chunk_chars=500)
    assert len(chunks) >= 2
    assert any("Условия отгрузки" in c for c in chunks)
    assert any("Условия оплаты" in c for c in chunks)


def test_split_markdown_headers_h1_h2_h3():
    doc = """# Политика компании
Вводная часть.

## Глава 1
Общие положения.

### Статья 1.1
Детализация положений.
"""
    chunks = split_markdown_by_headers_or_size(doc, max_chunk_chars=500)
    assert len(chunks) == 3
    assert "Политика компании" in chunks[0]
    assert "Глава 1" in chunks[1]
    assert "Статья 1.1" in chunks[2]


def test_chunking_preserves_header_in_subchunks():
    # Длинная секция с несколькими абзацами, превышающая max_chunk_chars
    p1 = "Абзац первый. " + "Сведения о регламенте. " * 10
    p2 = "Абзац второй. " + "Дополнительные правила. " * 10
    doc = f"## Регламент безопасности\n\n{p1}\n\n{p2}"

    chunks = split_markdown_by_headers_or_size(doc, max_chunk_chars=250, overlap_chars=30)
    assert len(chunks) >= 2
    # Каждый подчанк должен содержать заголовок секции для RAG-контекста
    for chunk in chunks:
        assert "## Регламент безопасности" in chunk
        assert len(chunk) <= 250


def test_chunking_overlap_is_applied():
    p1 = "Абзац 1: Кодовое слово ФЕНИКС на стыке чанков."
    p2 = "Абзац 2: Продолжение текста с другими деталями."
    doc = f"## Тест\n\n{p1}\n\n{p2}"

    chunks = split_markdown_by_headers_or_size(doc, max_chunk_chars=90, overlap_chars=25)
    assert len(chunks) >= 2
    # Проверяем, что хвостовой фрагмент p1 попал во второй чанк как перекрытие
    assert "ФЕНИКС" in chunks[0]
    assert "ФЕНИКС" in chunks[1]


def test_chunking_long_single_paragraph():
    long_p = "Слово " * 200  # ~1200 символов
    doc = f"### Статья\n\n{long_p}"

    chunks = split_markdown_by_headers_or_size(doc, max_chunk_chars=300, overlap_chars=50)
    assert len(chunks) >= 4
    for c in chunks:
        assert len(c) <= 300
        assert "### Статья" in c


def test_chunking_empty_and_crlf():
    assert split_markdown_by_headers_or_size("") == []
    assert split_markdown_by_headers_or_size("   \n\n  ") == []

    doc_crlf = "# H1\r\n\r\nТекст 1\r\n\r\n## H2\r\n\r\nТекст 2"
    chunks = split_markdown_by_headers_or_size(doc_crlf, max_chunk_chars=500)
    assert len(chunks) == 2
    assert "\r" not in chunks[0]
    assert "\r" not in chunks[1]
