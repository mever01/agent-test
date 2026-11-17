from pydantic import AnyHttpUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

GMAIL_CALLBACK_PATH = "/api/v1/gmail/oauth/callback"


class GmailConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    redirect_uri: AnyHttpUrl | None = Field(None, alias="GMAIL_OAUTH_REDIRECT_URI")
    frontend_url: AnyHttpUrl | None = Field(None, alias="GMAIL_FRONTEND_URL")
    encryption_key: SecretStr | None = Field(None, alias="GMAIL_ENCRYPTION_KEY")
    sync_interval_seconds: int = Field(60, ge=1, alias="GMAIL_SYNC_INTERVAL_SECONDS")

    @field_validator("redirect_uri", "frontend_url")
    @classmethod
    def validate_url(cls, url: AnyHttpUrl | None) -> AnyHttpUrl | None:
        if url is None:
            return None
        loopback = url.host in {"localhost", "127.0.0.1", "[::1]"}
        if (
            (url.scheme != "https" and not loopback)
            or url.username or url.password or url.query or url.fragment
        ):
            raise ValueError("Use an HTTPS URL or a local HTTP URL without query data")
        return url

    @field_validator("redirect_uri")
    @classmethod
    def validate_callback_path(cls, url: AnyHttpUrl | None) -> AnyHttpUrl | None:
        if url is not None and url.path != GMAIL_CALLBACK_PATH:
            raise ValueError(f"Use callback path {GMAIL_CALLBACK_PATH}")
        return url

    @property
    def frontend_origin(self) -> str | None:
        url = self.frontend_url
        if url is None:
            return None
        default_port = 443 if url.scheme == "https" else 80
        port = f":{url.port}" if url.port not in (None, default_port) else ""
        return f"{url.scheme}://{url.host}{port}"
