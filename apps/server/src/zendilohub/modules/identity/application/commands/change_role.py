from dataclasses import dataclass

from zendilohub.core.bus.message import Command
from zendilohub.core.domain.clock import Clock

from ...domain.exceptions import LastAdminError, OwnAccountError, UserNotFoundError
from ...domain.models.email import normalize_email
from ...domain.models.user import Role, User
from ...domain.ports.user_repository import UserRepository


@dataclass(frozen=True, kw_only=True)
class ChangeRole(Command[User]):
    """An administrator makes someone an administrator or a regular user."""

    actor_id: str
    user_id: str
    role: Role


@dataclass(frozen=True)
class MakeAdmin(Command[User]):
    """From the CLI: the way to the first administrator."""

    email: str


class ChangeRoleHandler:
    def __init__(self, users: UserRepository, clock: Clock) -> None:
        self._users = users
        self._clock = clock

    async def handle(self, command: ChangeRole) -> User:
        if command.actor_id == command.user_id:
            raise OwnAccountError()
        user = await self._users.find(command.user_id)
        if user is None:
            raise UserNotFoundError()
        if user.is_admin and command.role != 'admin' and await self._users.count_admins() <= 1:
            raise LastAdminError()
        user.change_role(command.role, self._clock.now())
        await self._users.save(user)
        return user


class MakeAdminHandler:
    def __init__(self, users: UserRepository, clock: Clock) -> None:
        self._users = users
        self._clock = clock

    async def handle(self, command: MakeAdmin) -> User:
        user = await self._users.find_by_email(normalize_email(command.email))
        if user is None:
            raise UserNotFoundError()
        user.change_role('admin', self._clock.now())
        await self._users.save(user)
        return user
