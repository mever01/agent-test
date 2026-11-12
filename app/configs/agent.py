from pydantic_settings import BaseSettings
from pydantic import Field

class AgentConfig(BaseSettings):
    max_iterations: int = Field(8, alias="AGENT_MAX_ITERATIONS")
    top_k_documents: int = Field(5, alias="AGENT_TOP_K_DOCUMENTS")
    top_k_threads: int = Field(5, alias="AGENT_TOP_K_THREADS")

