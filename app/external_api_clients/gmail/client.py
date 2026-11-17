from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote, urlencode

import httpx
from pydantic import BaseModel, Field, SecretStr, ValidationError

from app.external_api_clients.gmail.schemas import (
    GmailErrorResponse,
    GmailMessagePage,
    GmailPartBody,
    GmailThread,
    GoogleTokenError,
)

GMAIL_READONLY = "https://www.googleapis.com/auth/gmail.readonly"
_GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
_TOKEN_URL = "https://oauth2.googleapis.com/token"


class GmailReauthRequired(Exception):
    pass


class GmailRequestError(Exception):
    def __init__(self, status_code: int, retry_at: datetime | None = None) -> None:
        super().__init__(status_code)
        self.status_code = status_code
        self.retry_at = retry_at


def _retry_at(response: httpx.Response) -> datetime | None:
    value = response.headers.get("Retry-After")
    if not value:
        return None
    try:
        if value.isdecimal():
            return datetime.now(UTC) + timedelta(seconds=int(value))
        parsed = parsedate_to_datetime(value)
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except (ValueError, OverflowError, TypeError, OSError):
        return None


class GmailOAuthTokens(BaseModel):
    access_token: SecretStr = Field(min_length=1)
    refresh_token: SecretStr | None = Field(default=None, min_length=1)
    scope: str = ""


class GmailProfile(BaseModel):
    email_address: str = Field(alias="emailAddress", min_length=3, max_length=255)


class GmailClient:
    def __init__(self, http: httpx.AsyncClient, redirect_uri: str = "") -> None:
        self._http = http
        self._redirect_uri = redirect_uri

    def authorization_url(self, client_id: str, state: str, challenge: str) -> str:
        query = urlencode({
            "client_id": client_id,
            "redirect_uri": self._redirect_uri,
            "response_type": "code",
            "scope": GMAIL_READONLY,
            "access_type": "offline",
            "prompt": "consent select_account",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        })
        return f"https://accounts.google.com/o/oauth2/v2/auth?{query}"

    async def exchange_code(
        self, code: str, client_id: str, client_secret: str, verifier: str,
    ) -> GmailOAuthTokens:
        response = await self._http.post(
            _TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": self._redirect_uri,
            },
        )
        response.raise_for_status()
        return GmailOAuthTokens.model_validate_json(response.content)

    async def get_profile(self, access_token: SecretStr) -> GmailProfile:
        response = await self._http.get(
            f"{_GMAIL_API}/profile",
            headers={"Authorization": f"Bearer {access_token.get_secret_value()}"},
        )
        response.raise_for_status()
        return GmailProfile.model_validate_json(response.content)

    async def refresh(
        self, client_id: str, client_secret: SecretStr, refresh_token: SecretStr,
    ) -> GmailOAuthTokens:
        response = await self._http.post(
            _TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": client_id,
                "client_secret": client_secret.get_secret_value(),
                "refresh_token": refresh_token.get_secret_value(),
            },
        )
        if not response.is_success:
            if response.status_code == 400:
                try:
                    error = GoogleTokenError.model_validate_json(response.content)
                except ValidationError:
                    error = None
                if error and error.error in {"invalid_grant", "invalid_scope"}:
                    raise GmailReauthRequired
            raise GmailRequestError(response.status_code, _retry_at(response))
        tokens = GmailOAuthTokens.model_validate_json(response.content)
        if tokens.scope and GMAIL_READONLY not in tokens.scope.split():
            raise GmailReauthRequired
        return tokens

    async def list_messages(
        self,
        token: SecretStr,
        *,
        after: datetime,
        before: datetime,
        page_token: str | None,
    ) -> GmailMessagePage:
        # Gmail accepts Unix seconds. Include the lower boundary in the candidate set.
        start = int(after.timestamp()) - 1
        end = int(before.timestamp())
        return await self._get(
            GmailMessagePage,
            token,
            "messages",
            params={
                "q": f"after:{start} before:{end} -in:drafts",
                "includeSpamTrash": "false",
                "maxResults": "500",
                **({"pageToken": page_token} if page_token else {}),
            },
        )

    async def get_thread(self, token: SecretStr, thread_id: str) -> GmailThread:
        return await self._get(
            GmailThread, token, f"threads/{quote(thread_id, safe='')}",
            params={"format": "full"},
        )

    async def get_text_part(
        self, token: SecretStr, message_id: str, attachment_id: str,
    ) -> GmailPartBody:
        message = quote(message_id, safe="")
        attachment = quote(attachment_id, safe="")
        return await self._get(
            GmailPartBody, token, f"messages/{message}/attachments/{attachment}",
        )

    async def _get[T: BaseModel](
        self, schema: type[T], token: SecretStr, path: str,
        *, params: dict[str, str] | None = None,
    ) -> T:
        response = await self._http.get(
            f"{_GMAIL_API}/{path}",
            params=params,
            headers={"Authorization": f"Bearer {token.get_secret_value()}"},
        )
        if not response.is_success:
            if response.status_code == 403:
                _check_scope_error(response)
            raise GmailRequestError(response.status_code, _retry_at(response))
        return schema.model_validate_json(response.content)


def _check_scope_error(response: httpx.Response) -> None:
    try:
        payload = GmailErrorResponse.model_validate_json(response.content)
    except ValidationError:
        return
    if any(
        item.reason in {"insufficientPermissions", "ACCESS_TOKEN_SCOPE_INSUFFICIENT"}
        for item in (*payload.error.errors, *payload.error.details)
    ):
        raise GmailReauthRequired
