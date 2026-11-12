from pydantic_settings import BaseSettings
from pydantic import Field

class DatabaseConfig(BaseSettings):
    host: str = Field("localhost", alias="DB_HOST")
    port: int = Field(5432, alias="DB_PORT")
    user: str = Field("postgres", alias="DB_USER")
    password: str = Field("postgres", alias="DB_PASSWORD")
    name: str = Field("email_agent_db", alias="DB_NAME")
    pool_size: int = Field(10, alias="DB_POOL_SIZE")

    @property
    def async_url(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"

