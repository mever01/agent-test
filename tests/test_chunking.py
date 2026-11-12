from app.rag.chunking import split_markdown_by_headers_or_size

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

