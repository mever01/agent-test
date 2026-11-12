
import re
from collections.abc import Sequence

from app.db.schemas import MailMessage


QUOTE_HEADER_PATTERNS = (
    re.compile(
        r"^On\s+.+\s+wrote:\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^В\s+.+\s+написал(?:а)?:\s*$",
        re.IGNORECASE,
    ),
)

FORWARDED_MESSAGE_PATTERNS = (
    re.compile(
        r"^-{2,}\s*Original Message\s*-{2,}$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^-{2,}\s*Исходное сообщение\s*-{2,}$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^-{2,}\s*Forwarded message\s*-{2,}$",
        re.IGNORECASE,
    ),
)

SIGNATURE_PATTERNS = (
    re.compile(
        r"^--\s*$",
    ),
    re.compile(
        r"^(?:Best|Kind|Warm)\s+regards\s*,?\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^С уважением\s*,?\s*$",
        re.IGNORECASE,
    ),
)


def _matches_any(
    text: str,
    patterns: tuple[re.Pattern[str], ...],
) -> bool:
    return any(pattern.match(text) for pattern in patterns)


def clean_email_body(body: str) -> str:
    """Удаляет цитаты, историю пересылки и типовые подписи."""

    cleaned_lines: list[str] = []

    for line in body.splitlines():
        stripped = line.strip()

        if stripped.startswith(">"):
            continue

        if _matches_any(stripped, QUOTE_HEADER_PATTERNS):
            break

        if _matches_any(stripped, FORWARDED_MESSAGE_PATTERNS):
            break

        if _matches_any(stripped, SIGNATURE_PATTERNS):
            break

        cleaned_lines.append(line)

    return "\n".join(cleaned_lines).strip()


def format_cleaned_thread(
    messages: Sequence[MailMessage],
    min_body_length: int = 5,
) -> str:
    """Подготавливает очищенную переписку для LLM-суммаризации."""

    formatted_parts: list[str] = []

    for message in sorted(messages, key=lambda msg: msg.date):
        cleaned_body = clean_email_body(message.body)

        if len(cleaned_body) < min_body_length:
            continue

        date_str = message.date.strftime("%Y-%m-%d %H:%M")

        formatted_parts.append(
            f"[{date_str}] От: {message.sender} "
            f"-> Кому: {message.recipient}\n"
            f"Тема: {message.subject}\n"
            f"Текст:\n{cleaned_body}"
        )

    return "\n---\n".join(formatted_parts)
