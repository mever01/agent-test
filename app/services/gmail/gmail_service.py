from base64 import urlsafe_b64encode
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from uuid import UUID

import httpx
from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr
from sqlalchemy.exc import IntegrityError

from app.db.dao.gmail.gmail import GmailDAO
from app.db.enums import GmailConnectionStatus
from app.dto.gmail import (
    AuthorizedMailbox,
    ClaimedOAuthAttempt,
    GmailAccountInfo,
    GmailConnectionData,
    GmailOAuthStart,
    OAuthAttempt,
)
from app.external_api_clients.gmail.client import GMAIL_READONLY, GmailClient
from app.services.exceptions import GmailAccountNotFound, GmailConnectionConflict

OAUTH_TTL_SECONDS = 600


class GmailService:
    def __init__(self, dao: GmailDAO, client: GmailClient, cipher: Fernet) -> None:
        self._dao = dao
        self._client = client
        self._cipher = cipher

    async def create(self, owner_id: UUID, name: str) -> GmailAccountInfo:
        async with self._dao.transaction() as session:
            account = await self._dao.create_account(session, owner_id, name)
            return GmailAccountInfo(
                account.id, account.name, None, GmailConnectionStatus.PENDING, None,
            )

    async def list_accounts(self, owner_id: UUID) -> list[GmailAccountInfo]:
        async with self._dao.transaction() as session:
            accounts = await self._dao.list_accounts(session, owner_id)
            return [
                GmailAccountInfo(
                    id=account.id,
                    name=account.name,
                    gmail_email=account.gmail_email,
                    status=(
                        connection.status
                        if connection else GmailConnectionStatus.PENDING
                    ),
                    last_success_at=connection.last_success_at if connection else None,
                )
                for account, connection in accounts
            ]

    async def configure(
        self, owner_id: UUID, account_id: UUID,
        client_id: str, client_secret: SecretStr,
    ) -> None:
        ciphertext = self._encrypt(client_secret.get_secret_value())
        async with self._dao.transaction() as session:
            account = await self._dao.lock_account(
                session, account_id, owner_id=owner_id,
            )
            if account is None:
                raise GmailAccountNotFound
            connection = await self._dao.lock_connection(session, account_id)
            if connection is None:
                connection = await self._dao.create_connection(session, account_id)
            connection.pending_client_id = client_id
            connection.pending_client_secret_ciphertext = ciphertext
            _clear_attempt(connection)
            await self._dao.save_connection(session, connection)

    async def start(self, owner_id: UUID, account_id: UUID) -> GmailOAuthStart:
        state = token_urlsafe(32)
        browser_token = token_urlsafe(48)
        browser_hash = sha256(browser_token.encode())
        attempt = OAuthAttempt(
            state_digest=sha256(state.encode()).hexdigest(),
            browser_digest=browser_hash.hexdigest(),
            expires_at=datetime.now(UTC) + timedelta(seconds=OAUTH_TTL_SECONDS),
        )
        async with self._dao.transaction() as session:
            account = await self._dao.lock_account(
                session, account_id, owner_id=owner_id,
            )
            if account is None:
                raise GmailAccountNotFound
            connection = await self._dao.lock_connection(session, account_id)
            if connection is None:
                raise GmailConnectionConflict
            client_id = connection.pending_client_id or connection.client_id
            if not client_id:
                raise GmailConnectionConflict
            connection.oauth_state_digest = attempt.state_digest
            connection.oauth_browser_digest = attempt.browser_digest
            connection.oauth_expires_at = attempt.expires_at
            await self._dao.save_connection(session, connection)

        challenge = urlsafe_b64encode(browser_hash.digest()).rstrip(b"=").decode()
        return GmailOAuthStart(
            self._client.authorization_url(client_id, state, challenge), browser_token,
        )

    async def _claim_attempt(
        self, state: str, browser_token: str,
    ) -> ClaimedOAuthAttempt | None:
        async with self._dao.transaction() as session:
            connection = await self._dao.lock_oauth_attempt(
                session,
                sha256(state.encode()).hexdigest(),
                sha256(browser_token.encode()).hexdigest(),
                datetime.now(UTC),
            )
            if connection is None:
                return None
            connection.oauth_state_digest = None
            client_id = connection.pending_client_id or connection.client_id
            secret = (
                connection.pending_client_secret_ciphertext
                or connection.client_secret_ciphertext
            )
            await self._dao.save_connection(session, connection)
            if not client_id or not secret:
                return None
            return ClaimedOAuthAttempt(
                connection.gmail_account_id, client_id, secret,
                connection.oauth_browser_digest,
            )

    async def complete(
        self, state: str, browser_token: str, code: str | None,
    ) -> bool:
        attempt = await self._claim_attempt(state, browser_token)
        if attempt is None or not code:
            return False
        try:
            client_secret = self._cipher.decrypt(attempt.secret_ciphertext).decode()
            tokens = await self._client.exchange_code(
                code, attempt.client_id, client_secret, browser_token,
            )
            scopes = tokens.scope.split()
            if GMAIL_READONLY not in scopes:
                return False
            profile = await self._client.get_profile(tokens.access_token)
            await self._activate(
                attempt,
                AuthorizedMailbox(
                    gmail_email=profile.email_address.strip().lower(),
                    scopes=scopes,
                    refresh_token_ciphertext=(
                        self._encrypt(tokens.refresh_token.get_secret_value())
                        if tokens.refresh_token else None
                    ),
                ),
            )
        except (
            InvalidToken, httpx.HTTPError, ValueError,
            GmailConnectionConflict, IntegrityError,
        ):
            return False
        return True

    async def _activate(
        self, attempt: ClaimedOAuthAttempt, mailbox: AuthorizedMailbox,
    ) -> None:
        async with self._dao.transaction() as session:
            account = await self._dao.lock_account(session, attempt.account_id)
            connection = await self._dao.lock_connection(session, attempt.account_id)
            if (
                account is None or connection is None
                or connection.oauth_browser_digest != attempt.browser_digest
            ):
                raise GmailConnectionConflict
            if account.gmail_email and account.gmail_email != mailbox.gmail_email:
                raise GmailConnectionConflict

            refresh_token = mailbox.refresh_token_ciphertext
            if (
                refresh_token is None and account.gmail_email == mailbox.gmail_email
                and connection.client_id == attempt.client_id
                and connection.status != GmailConnectionStatus.REAUTH_REQUIRED
            ):
                refresh_token = connection.refresh_token_ciphertext
            if not refresh_token:
                raise GmailConnectionConflict

            account.gmail_email = mailbox.gmail_email
            connection.client_id = attempt.client_id
            connection.client_secret_ciphertext = attempt.secret_ciphertext
            connection.refresh_token_ciphertext = refresh_token
            connection.scopes = mailbox.scopes
            connection.status = GmailConnectionStatus.CONNECTED
            connection.next_sync_at = datetime.now(UTC)
            connection.pending_client_id = None
            connection.pending_client_secret_ciphertext = None
            _invalidate_lease(connection)
            _clear_attempt(connection)
            await self._dao.save_account(session, account)
            await self._dao.save_connection(session, connection)

    async def disconnect(self, owner_id: UUID, account_id: UUID) -> None:
        async with self._dao.transaction() as session:
            account = await self._dao.lock_account(
                session, account_id, owner_id=owner_id,
            )
            if account is None:
                raise GmailAccountNotFound
            connection = await self._dao.lock_connection(session, account_id)
            if connection is None:
                connection = await self._dao.create_connection(session, account_id)
            connection.client_id = None
            connection.client_secret_ciphertext = None
            connection.refresh_token_ciphertext = None
            connection.pending_client_id = None
            connection.pending_client_secret_ciphertext = None
            connection.scopes = []
            connection.status = GmailConnectionStatus.DISCONNECTED
            connection.next_sync_at = None
            _invalidate_lease(connection)
            _clear_attempt(connection)
            await self._dao.save_connection(session, connection)

    def _encrypt(self, secret: str) -> str:
        return self._cipher.encrypt(secret.encode()).decode()


def _clear_attempt(connection: GmailConnectionData) -> None:
    connection.oauth_state_digest = None
    connection.oauth_browser_digest = None
    connection.oauth_expires_at = None


def _invalidate_lease(connection: GmailConnectionData) -> None:
    connection.generation += 1
    connection.lease_token = None
    connection.lease_expires_at = None
