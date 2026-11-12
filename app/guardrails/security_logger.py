import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from app.configs import settings
from app.guardrails.schemas import SecurityEventLog

def log_canary_leak(
    run_id: str,
    location: Literal["tool_call_arguments", "model_response"],
    log_file_path: Path | None = None,
) -> SecurityEventLog:
    """
    Записывает событие SYSTEM_PROMPT_LEAK в security_events.jsonl строго по ТЗ:
    - время UTC
    - run_id
    - место обнаружения: 'tool_call_arguments' или 'model_response'
    - reason=CANARY_MATCH
    - action=BLOCKED
    
    КРИТИЧЕСКОЕ ТРЕБОВАНИЕ ТЗ:
    В логи НЕ должны попадать активные токены, полный промпт и содержимое заблокированного ответа!
    """
    path = log_file_path or settings.guardrails.security_log_path

    # Формируем событие строго по контракту
    event = SecurityEventLog(
        timestamp=datetime.now(timezone.utc).isoformat(),
        run_id=run_id,
        location=location,
        reason="CANARY_MATCH",
        action="BLOCKED",
    )

    # Атомарная дозапись строки JSONL
    line = json.dumps(event.model_dump(), ensure_ascii=False) + "\n"
    with open(path, mode="a", encoding="utf-8") as f:
        f.write(line)

    return event

