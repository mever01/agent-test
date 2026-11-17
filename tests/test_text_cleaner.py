from app.services.rag.ingestion.email.text_cleaner import clean_email_body

def test_clean_email_body_strips_quotes_and_signatures():
    raw_body = """Здравствуйте! Согласуем дату 25 ноября.

> On 12.10, John wrote:
> Пришлите сроки поставки
> Спасибо!

--
С уважением,
Иван Смирнов
Руководитель IT"""

    cleaned = clean_email_body(raw_body)
    assert "Согласуем дату 25 ноября." in cleaned
    assert "John wrote:" not in cleaned
    assert "Пришлите сроки" not in cleaned
    assert "Руководитель IT" not in cleaned
