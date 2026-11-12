import re

SUSPICIOUS_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior)\s+instructions",
    r"забудь\s+(все\s+)?(предыдущие|прошлые)\s+инструкции",
    r"print\s+(your\s+)?(system\s+prompt|canary)",
    r"выведи\s+(свой\s+)?(системный\s+промпт|канарейк|токен)",
    r"system\s*:\s*",
    r"<\s*system\s*>",
    r"reveal\s+(secret|token|instructions)",
]

def detect_prompt_injection(text: str) -> tuple[bool, str | None]:
    """
    Быстрая эвристическая проверка входящего пользовательского запроса на попытку Prompt Injection.
    """
    for pattern in SUSPICIOUS_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return True, f"Обнаружен подозрительный паттерн: {match.group(0)}"
    return False, None

