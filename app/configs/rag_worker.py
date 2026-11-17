from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RagWorkerConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    indexing_delay_minutes: int = Field(
        30, ge=0, alias="RAG_WORKER_INDEXING_DELAY_MINUTES",
    )
