import re

PHONE_PATTERN = r"(?:\+7|8)[\s\-]?[0-9]{3}[\s\-]?[0-9]{3}[\s\-]?[0-9]{2}[\s\-]?[0-9]{2}\b"
CARD_PATTERN = r"\b[0-9]{4}[\s\-]?[0-9]{4}[\s\-]?[0-9]{4}[\s\-]?[0-9]{4}\b"

def mask_pii(text: str) -> str:
    """Маскирование персональных данных (телефоны, номера карт)."""
    text = re.sub(PHONE_PATTERN, "[PHONE_MASKED]", text)
    text = re.sub(CARD_PATTERN, "[CARD_MASKED]", text)
    return text

