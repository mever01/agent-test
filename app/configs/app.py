from pydantic_settings import BaseSettings
from pydantic import Field

class AppConfig(BaseSettings):
    title: str = "Email Security AI Agent"
    version: str = "0.1.0"
    debug: bool = Field(False, alias="DEBUG")
    host: str = Field("0.0.0.0", alias="APP_HOST")
    port: int = Field(8000, alias="APP_PORT")

