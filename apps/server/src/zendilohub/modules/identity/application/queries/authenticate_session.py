from dataclasses import dataclass

from zendilohub.core.bus.message import Query
from zendilohub.core.domain.clock import Clock

from ...domain.models.session import Session
from ...domain.models.user import User
from ...domain.ports.session_repository import SessionRepository
from ...domain.ports.token_service import TokenService
from ...domain.ports.user_repository import UserRepository


@dataclass(frozen=True)
class AuthenticatedSession:
    user: User
    session: Session


@dataclass(frozen=True)
class AuthenticateSession(Query[AuthenticatedSession | None]):
    token: str


class AuthenticateSessionHandler:
    def __init__(self, users: UserRepository, sessions: SessionRepository, tokens: TokenService, clock: Clock) -> None:
        self._users = users
        self._sessions = sessions
        self._tokens = tokens
        self._clock = clock

    async def handle(self, query: AuthenticateSession) -> AuthenticatedSession | None:
        session = await self._sessions.find(self._tokens.id_of(query.token))
        if session is None:
            return None
        if session.is_expired(self._clock.now()):
            await self._sessions.delete(session.id)
            return None
        user = await self._users.find(session.user_id)
        return AuthenticatedSession(user, session) if user else None
