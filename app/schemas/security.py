from pydantic import BaseModel
from typing import Literal

class SecurityEventLog(BaseModel):
    timestamp: str # UTC ISO 8601
    run_id: str
    location: Literal["tool_call_arguments", "model_response"]
    reason: Literal["CANARY_MATCH"] = "CANARY_MATCH"
    action: Literal["BLOCKED"] = "BLOCKED"

