import json
from app.guardrails.outbound.canary_detector import is_canary_leaked

def check_tool_calls_for_canary(tool_calls: list[dict], canary_token: str) -> bool:
    """
    Проверяет все декодированные аргументы вызовов инструментов на наличие Canary Token.
    """
    if not canary_token:
        return False

    for tc in tool_calls:
        args = tc.get("args")
        if isinstance(args, dict):
            args_str = json.dumps(args, ensure_ascii=False)
        elif isinstance(args, str):
            args_str = args
        else:
            args_str = str(args)

        if is_canary_leaked(args_str, canary_token):
            return True

    return False

