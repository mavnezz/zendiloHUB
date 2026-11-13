from dataclasses import dataclass
from datetime import datetime

from zendilohub.core.domain.clock import Clock

from ...domain.models.session import Session
from ...domain.models.user import User
from ...domain.ports.session_repository import SessionRepository
from ...domain.ports.token_service import TokenService


@dataclass(frozen=True)
class LoginResult:
    token: str
    """The session token for the cookie."""
    user: User
    expires_at: datetime


class SessionStarter:
    """Logs a user in: after the login itself, a confirmed sign-up or a password reset."""

    def __init__(self, sessions: SessionRepository, tokens: TokenService, clock: Clock) -> None:
        self._sessions = sessions
        self._tokens = tokens
        self._clock = clock

    async def start(self, user: User) -> LoginResult:
        now = self._clock.now()
        await self._sessions.delete_expired(now)
        issued = self._tokens.issue()
        session = Session.start(id=issued.id, user_id=user.id, now=now)
        await self._sessions.save(session)
        return LoginResult(issued.token, user, session.expires_at)
