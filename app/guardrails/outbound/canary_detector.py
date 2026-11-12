def is_canary_leaked(text: str | None, canary_token: str) -> bool:
    """
    Детерминированная проверка строки на наличие активного Canary Token как подстроки.
    Выполняется кодом без участия LLM.
    """
    if not text or not canary_token:
        return False
    return canary_token in text

