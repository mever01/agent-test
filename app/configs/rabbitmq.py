from pydantic_settings import BaseSettings
from pydantic import Field

class RabbitMQConfig(BaseSettings):
    url: str = Field("amqp://guest:guest@localhost:5672/", alias="RABBITMQ_URL")
    threads_queue: str = Field("rag.threads.queue", alias="RABBITMQ_THREADS_QUEUE")
    documents_queue: str = Field("rag.documents.queue", alias="RABBITMQ_DOCUMENTS_QUEUE")
    exchange: str = Field("rag.events", alias="RABBITMQ_EXCHANGE")
    dlq_queue: str = Field("rag.ingestion.dlq", alias="RABBITMQ_DLQ")

