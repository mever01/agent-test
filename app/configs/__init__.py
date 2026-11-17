from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr

from app.configs.app import AppConfig
from app.configs.database import DatabaseConfig
from app.configs.rabbitmq import RabbitMQConfig
from app.configs.embedding import EmbeddingConfig
from app.configs.llm import LLMConfig
from app.configs.guardrails import GuardrailsConfig
from app.configs.agent import AgentConfig
from app.configs.gmail import GmailConfig
from app.configs.rag_worker import RagWorkerConfig

class Settings(BaseSettings):
    app: AppConfig = Field(default_factory=AppConfig)
    db: DatabaseConfig = Field(default_factory=DatabaseConfig)
    rabbitmq: RabbitMQConfig = Field(default_factory=RabbitMQConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    guardrails: GuardrailsConfig = Field(default_factory=GuardrailsConfig)
    auth_session_ttl: int = Field(3600, gt=0)
    seed_user_email: str = Field(
        "manager@example.org",
        min_length=1,
        max_length=255
    )
    seed_user_password: SecretStr = Field(
        default=SecretStr("AgentDemo-2026!"),
        min_length=12,
        max_length=256,
    )
    agent: AgentConfig = Field(default_factory=AgentConfig)
    gmail: GmailConfig = Field(default_factory=GmailConfig)
    rag_worker: RagWorkerConfig = Field(default_factory=RagWorkerConfig)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()

__all__ = ["Settings", "settings", "get_settings"]

