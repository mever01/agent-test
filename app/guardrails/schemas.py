from typing import Literal
from pydantic import BaseModel


class SecurityEventLog(BaseModel):
    event_type: Literal["SYSTEM_PROMPT_LEAK"] = "SYSTEM_PROMPT_LEAK"
    timestamp: str
    run_id: str
    location: Literal["tool_call_arguments", "model_response"]
    reason: Literal["CANARY_MATCH"] = "CANARY_MATCH"
    action: Literal["BLOCKED"] = "BLOCKED"
