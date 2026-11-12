from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

from app.configs.app import AppConfig
from app.configs.database import DatabaseConfig
from app.configs.rabbitmq import RabbitMQConfig
from app.configs.embedding import EmbeddingConfig
from app.configs.llm import LLMConfig
from app.configs.guardrails import GuardrailsConfig
from app.configs.agent import AgentConfig

class Settings(BaseSettings):
    app: AppConfig = Field(default_factory=AppConfig)
    db: DatabaseConfig = Field(default_factory=DatabaseConfig)
    rabbitmq: RabbitMQConfig = Field(default_factory=RabbitMQConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    guardrails: GuardrailsConfig = Field(default_factory=GuardrailsConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)

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

