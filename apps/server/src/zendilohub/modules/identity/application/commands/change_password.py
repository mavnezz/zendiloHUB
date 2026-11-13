from dataclasses import dataclass

from zendilohub.core.bus.message import Command
from zendilohub.core.domain.clock import Clock

from ...domain.exceptions import InvalidCurrentPasswordError, UserNotFoundError
from ...domain.models.password_policy import check_password
from ...domain.ports.password_hasher import PasswordHasher
from ...domain.ports.session_repository import SessionRepository
from ...domain.ports.user_repository import UserRepository


@dataclass(frozen=True, kw_only=True)
class ChangePassword(Command[None]):
    """Changes the password and ends the user's other sessions."""

    user_id: str
    session_id: str
    current_password: str
    new_password: str


class ChangePasswordHandler:
    def __init__(
        self, users: UserRepository, sessions: SessionRepository, hasher: PasswordHasher, clock: Clock
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._hasher = hasher
        self._clock = clock

    async def handle(self, command: ChangePassword) -> None:
        user = await self._users.find(command.user_id)
        if user is None:
            raise UserNotFoundError()
        if not await self._hasher.verify(command.current_password, user.password_hash):
            raise InvalidCurrentPasswordError()
        check_password(command.new_password)
        user.change_password(await self._hasher.hash(command.new_password), self._clock.now())
        await self._users.save(user)
        await self._sessions.delete_for_user(user.id, except_session=command.session_id)
