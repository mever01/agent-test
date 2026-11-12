from pydantic_settings import BaseSettings
from pydantic import Field

class LLMConfig(BaseSettings):
    url: str = Field(
        "http://localhost:11435/v1/chat/completions", 
        alias="LLM_URL"
    )
    model_name: str = Field("qwen2.5:7b", alias="LLM_MODEL")
    api_key: str | None = Field(None, alias="LLM_API_KEY")
    temperature: float = Field(0.1, alias="LLM_TEMPERATURE")
    timeout: float = Field(600.0, alias="LLM_TIMEOUT", gt=0)

