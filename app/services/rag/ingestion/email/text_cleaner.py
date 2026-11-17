
import re


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


def clean_email_body(body: str, *, keep_forwarded: bool = False) -> str:
    """Удаляет цитаты и подписи; при keep_forwarded сохраняет пересылку."""

    cleaned_lines: list[str] = []

    for line in body.splitlines():
        stripped = line.strip()

        if stripped.startswith(">"):
            continue

        if _matches_any(stripped, QUOTE_HEADER_PATTERNS):
            break

        if _matches_any(stripped, FORWARDED_MESSAGE_PATTERNS):
            if keep_forwarded:
                continue
            break

        if _matches_any(stripped, SIGNATURE_PATTERNS):
            break

        cleaned_lines.append(line)

    return "\n".join(cleaned_lines).strip()
