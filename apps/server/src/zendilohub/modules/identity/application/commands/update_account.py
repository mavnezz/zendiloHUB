from dataclasses import dataclass

from zendilohub.core.bus.message import Command
from zendilohub.core.domain.clock import Clock

from ...domain.exceptions import UserNotFoundError
from ...domain.models.user import Locale, User
from ...domain.ports.user_repository import UserRepository


@dataclass(frozen=True, kw_only=True)
class UpdateAccount(Command[User]):
    user_id: str
    locale: Locale


class UpdateAccountHandler:
    def __init__(self, users: UserRepository, clock: Clock) -> None:
        self._users = users
        self._clock = clock

    async def handle(self, command: UpdateAccount) -> User:
        user = await self._users.find(command.user_id)
        if user is None:
            raise UserNotFoundError()
        user.change_locale(command.locale, self._clock.now())
        await self._users.save(user)
        return user
