from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path

class GuardrailsConfig(BaseSettings):
    security_log_path: Path = Field(
        Path("security_events.jsonl"), 
        alias="SECURITY_EVENTS_PATH"
    )
    canary_token_prefix: str = Field("CANARY_SEC_", alias="CANARY_PREFIX")
    max_user_message_length: int = Field(4000, alias="MAX_USER_MESSAGE_LENGTH")
    enable_pii_masking: bool = Field(True, alias="ENABLE_PII_MASKING")

