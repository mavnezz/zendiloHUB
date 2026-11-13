import asyncio
import hashlib
import secrets

import argon2
from argon2.exceptions import InvalidHashError, VerificationError

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.http.access import Principal

from ..application.queries.authenticate_session import AuthenticateSession
from ..domain.ports.token_service import IssuedToken


class Argon2PasswordHasher:
    """Argon2id with argon2-cffi's defaults (RFC 9106 low-memory profile); hashing runs in a thread."""

    def __init__(self, hasher: argon2.PasswordHasher | None = None) -> None:
        self._hasher = hasher or argon2.PasswordHasher()

    async def hash(self, password: str) -> str:
        return await asyncio.to_thread(self._hasher.hash, password)

    async def verify(self, password: str, password_hash: str) -> bool:
        try:
            return await asyncio.to_thread(self._hasher.verify, password_hash, password)
        except VerificationError, InvalidHashError:
            return False

    def needs_rehash(self, password_hash: str) -> bool:
        try:
            return self._hasher.check_needs_rehash(password_hash)
        except InvalidHashError:
            return True


class Sha256TokenService:
    """Random tokens; only their SHA-256 is stored, so a leaked database does not leak usable tokens."""

    def issue(self) -> IssuedToken:
        token = secrets.token_urlsafe(32)
        return IssuedToken(token, self.id_of(token))

    def id_of(self, token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()


class SessionAuthGuard:
    def __init__(self, bus: CommandBus) -> None:
        self._bus = bus

    async def authenticate(self, session_token: str) -> Principal | None:
        result = await self._bus.query(AuthenticateSession(session_token))
        if result is None:
            return None
        return Principal(
            user_id=result.user.id, email=result.user.email, role=result.user.role, session_id=result.session.id
        )
