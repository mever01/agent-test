import re
from app.schemas.email import EmailMessage

def clean_email_body(body: str) -> str:
    """
    Очистка тела одного письма от цитат, хвостов пересылки и стандартных подписей.
    """
    lines = body.split("\n")
    cleaned_lines = []

    for line in lines:
        stripped = line.strip()
        # 1. Пропускаем строки цитирования с символом >
        if stripped.startswith(">"):
            continue
        # 2. Пропускаем заголовки цитирования вида "On ... wrote:" или "В ... написал:"
        if re.match(r"^(On|В|Среда|Четверг|Пятница|Понедельник|Вторник|Суббота|Воскресенье).+wrote:?", stripped, re.IGNORECASE):
            break
        if "-----Original Message-----" in line or "---- Исходное сообщение ----" in line:
            break
        # 3. Отсекаем стандартные разделители подписей
        if stripped == "--" or stripped == "---":
            break
        if re.match(r"^(С уважением|Best regards|Kind regards),?$", stripped, re.IGNORECASE):
            break

        cleaned_lines.append(line)

    cleaned_text = "\n".join(cleaned_lines).strip()
    return cleaned_text

def format_cleaned_thread(messages: list[EmailMessage]) -> str:
    """
    Форматирует цепочку писем в очищенный текст для структурированной суммаризации.
    """
    formatted_parts = []
    for msg in messages:
        cleaned_body = clean_email_body(msg.body)
        if len(cleaned_body.strip()) < 5:
            continue
        date_str = msg.date.strftime("%Y-%m-%d %H:%M")
        formatted_parts.append(
            f"[{date_str}] От: {msg.sender} -> Кому: {msg.recipient}\n"
            f"Тема: {msg.subject}\n"
            f"Текст:\n{cleaned_body}\n"
        )
    return "\n---\n".join(formatted_parts)

