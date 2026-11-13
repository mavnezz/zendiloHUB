from dataclasses import dataclass

from zendilohub.core.bus.message import Command

from ...domain.ports.session_repository import SessionRepository
from ...domain.ports.token_service import TokenService


@dataclass(frozen=True)
class Logout(Command[None]):
    token: str


class LogoutHandler:
    def __init__(self, sessions: SessionRepository, tokens: TokenService) -> None:
        self._sessions = sessions
        self._tokens = tokens

    async def handle(self, command: Logout) -> None:
        await self._sessions.delete(self._tokens.id_of(command.token))
