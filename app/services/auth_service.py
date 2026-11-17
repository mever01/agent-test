import asyncio
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from time import monotonic
from uuid import UUID

from app.db.models.user import User
from app.db.dao.user import UserRepository
from app.dto.auth import Session


def _derive_password(password: str, salt: bytes) -> str:
    return hashlib.scrypt(
        password.encode(), salt=salt, n=2**15, r=8, p=3, maxmem=64 * 1024**2,
    ).hex()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    return f"{salt.hex()}:{_derive_password(password, salt)}"


def verify_password(password: str, stored_hash: str | None) -> bool:
    salt, separator, digest = (stored_hash or "").partition(":")
    try:
        salt_bytes = bytes.fromhex(salt) if separator else bytes(16)
    except ValueError:
        return False
    candidate = _derive_password(password, salt_bytes)
    return bool(separator and hmac.compare_digest(candidate, digest))


def _session_key(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

class AuthService:
    def __init__(self, users: UserRepository, ttl_seconds: int) -> None:
        self._users = users
        self._ttl_seconds = ttl_seconds
        self._sessions: dict[str, Session] = {}

    async def login(self, email: str, password: str) -> str | None:
        email = email.strip().lower()
        if not 1 <= len(email) <= 255 or not 1 <= len(password) <= 256:
            return None
        user = await self._users.by_email(email)
        stored_hash = user.password_hash if user else None
        valid = await asyncio.to_thread(verify_password, password, stored_hash)
        if user is None or not valid:
            return None

        now = monotonic()
        self._sessions = {
            key: session for key, session in self._sessions.items() if session.expires_at > now
        }
        token = secrets.token_urlsafe(32)
        self._sessions[_session_key(token)] = Session(user.id, now + self._ttl_seconds)
        return token

    async def authenticate(self, token: str) -> User | None:
        if len(token) != 43:
            return None
        key = _session_key(token)
        session = self._sessions.get(key)
        if session is None:
            return None
        if session.expires_at <= monotonic():
            self._sessions.pop(key, None)
            return None
        user = await self._users.by_id(session.user_id)
        return user if user and user.password_hash else None
