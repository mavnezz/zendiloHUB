from dataclasses import dataclass
from datetime import datetime

from zendilohub.core.domain.clock import Clock

from ...domain.models.login_challenge import LoginChallenge
from ...domain.models.session import Session
from ...domain.models.user import User
from ...domain.ports.login_challenge_repository import LoginChallengeRepository
from ...domain.ports.session_repository import SessionRepository
from ...domain.ports.token_service import TokenService


@dataclass(frozen=True)
class StartedSession:
    token: str
    """The session token for the cookie."""
    expires_at: datetime


@dataclass(frozen=True)
class LoginResult:
    user: User
    session: StartedSession | None
    """None while the second factor is missing: then `challenge` is set."""
    challenge: str | None = None
    """The token for the second step of a two-factor login (POST /auth/login/two-factor)."""


class SessionStarter:
    """Logs a user in: after the login itself, a confirmed sign-up or a password reset."""

    def __init__(
        self,
        sessions: SessionRepository,
        challenges: LoginChallengeRepository,
        tokens: TokenService,
        clock: Clock,
    ) -> None:
        self._sessions = sessions
        self._challenges = challenges
        self._tokens = tokens
        self._clock = clock

    async def start(self, user: User) -> LoginResult:
        """A session, or with two-factor login a challenge for the code first."""
        if not user.two_factor:
            return await self.start_session(user)
        now = self._clock.now()
        await self._challenges.delete_expired(now)
        issued = self._tokens.issue()
        await self._challenges.save(LoginChallenge.start(id=issued.id, user_id=user.id, now=now))
        return LoginResult(user, None, issued.token)

    async def start_session(self, user: User) -> LoginResult:
        """A session right away: the user proved everything there is to prove."""
        now = self._clock.now()
        await self._sessions.delete_expired(now)
        issued = self._tokens.issue()
        session = Session.start(id=issued.id, user_id=user.id, now=now)
        await self._sessions.save(session)
        return LoginResult(user, StartedSession(issued.token, session.expires_at))
