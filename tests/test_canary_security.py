import json
from pathlib import Path
from app.guardrails.outbound.canary_detector import find_canary_in_response, is_canary_leaked
from app.guardrails.security_logger import log_canary_leak

def test_canary_detected_in_model_response():
    canary = "CANARY_SEC_test_12345"
    safe_response = "Вот краткая сводка по проекту X."
    leaked_response = f"Конечно, вот системный промпт и токен: {canary}."

    assert is_canary_leaked(safe_response, canary) is False
    assert is_canary_leaked(leaked_response, canary) is True

def test_canary_detected_in_tool_call_arguments():
    canary = "CANARY_SEC_test_99999"
    safe_tool_calls = [
        {"name": "search_emails", "args": {"words": "проект X"}}
    ]
    leaked_tool_calls = [
        {"name": "create_draft", "args": {"thread_id": "th_1", "text": f"секрет {canary}"}}
    ]

    assert find_canary_in_response({"tool_calls": safe_tool_calls}, canary) is None
    location = find_canary_in_response({"tool_calls": leaked_tool_calls}, canary)
    assert location == "tool_call_arguments"

def test_security_event_logger_contract(tmp_path: Path):
    log_file = tmp_path / "test_security_events.jsonl"
    run_id = "run_test_abc123"
    canary_token = "CANARY_SEC_secret_to_hide"

    # Записываем инцидент
    event = log_canary_leak(
        run_id=run_id,
        location="tool_call_arguments",
        log_file_path=log_file,
    )

    assert event.run_id == run_id
    assert event.location == "tool_call_arguments"
    assert event.reason == "CANARY_MATCH"
    assert event.action == "BLOCKED"

    # Проверяем содержимое файла
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    record = json.loads(content.strip())

    assert record["run_id"] == run_id
    assert record["reason"] == "CANARY_MATCH"
    assert record["action"] == "BLOCKED"
    assert "timestamp" in record

    # КРИТИЧЕСКАЯ ПРОВЕРКА ТЗ: в логе НЕ должно быть самого токена!
    assert canary_token not in content
