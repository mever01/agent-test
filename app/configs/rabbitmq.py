from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RabbitMQConfig(BaseSettings):
    """Конфигурация подключения к брокеру сообщений RabbitMQ."""
    url: str = Field("amqp://guest:guest@localhost:5672/", alias="RABBITMQ_URL")
    exchange: str = Field("rag.events", alias="RABBITMQ_EXCHANGE")
    dlq_exchange: str = Field("rag.events.dlx", alias="RABBITMQ_DLQ_EXCHANGE")
    threads_queue: str = Field("rag.threads.queue", alias="RABBITMQ_THREADS_QUEUE")
    documents_queue: str = Field("rag.documents.queue", alias="RABBITMQ_DOCUMENTS_QUEUE")
    dlq_queue: str = Field("rag.dead.queue", alias="RABBITMQ_DLQ")

    # Параметры надежности и производительности
    prefetch_count: int = Field(2, alias="RABBITMQ_PREFETCH_COUNT")
    connect_attempts: int = Field(20, alias="RABBITMQ_CONNECT_ATTEMPTS")
    retry_delay_seconds: float = Field(2.0, alias="RABBITMQ_RETRY_DELAY_SECONDS")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
