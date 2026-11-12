from datetime import datetime
from app.rag.text_cleaner import clean_email_body, format_cleaned_thread
from app.schemas.email import EmailMessage

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

def test_format_cleaned_thread():
    messages = [
        EmailMessage(
            id="msg_1",
            thread_id="th_1",
            sender="client@corp.ru",
            recipient="manager@mycorp.ru",
            date=datetime(2026, 11, 1, 10, 0),
            subject="Вопрос по поставке",
            body="Интересуют сроки отгрузки партии.",
        ),
        EmailMessage(
            id="msg_2",
            thread_id="th_1",
            sender="manager@mycorp.ru",
            recipient="client@corp.ru",
            date=datetime(2026, 11, 2, 11, 0),
            subject="Re: Вопрос по поставке",
            body="Срок отгрузки — 25 ноября.\n\n--\nС уважением, Менеджер",
        ),
    ]

    formatted = format_cleaned_thread(messages)
    assert "Интересуют сроки отгрузки" in formatted
    assert "Срок отгрузки — 25 ноября." in formatted
    assert "С уважением, Менеджер" not in formatted

