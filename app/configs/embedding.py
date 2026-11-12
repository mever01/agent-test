from pydantic_settings import BaseSettings
from pydantic import Field

class EmbeddingConfig(BaseSettings):
    url: str = Field(
        "http://localhost:11434/api/embeddings", 
        alias="EMBEDDING_URL"
    )
    model_name: str = Field("qwen3-embedding:0.6b", alias="EMBEDDING_MODEL")
    dimension: int = Field(1024, alias="EMBEDDING_DIMENSION")
    api_key: str | None = Field(None, alias="EMBEDDING_API_KEY")
    batch_size: int = Field(32, alias="EMBEDDING_BATCH_SIZE")

