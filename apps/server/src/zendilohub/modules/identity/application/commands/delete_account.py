from dataclasses import dataclass

from zendilohub.core.bus.message import Command
from zendilohub.core.domain.transaction import TransactionManager
from zendilohub.core.events.event_bus import EventBus
from zendilohub.core.events.integration_events import UserDeleted

from ...domain.exceptions import InvalidCurrentPasswordError, LastAdminError, OwnAccountError, UserNotFoundError
from ...domain.models.user import User
from ...domain.ports.password_hasher import PasswordHasher
from ...domain.ports.user_repository import UserRepository


@dataclass(frozen=True, kw_only=True)
class DeleteAccount(Command[None]):
    """A user deletes their own account; the password confirms it."""

    user_id: str
    password: str


@dataclass(frozen=True, kw_only=True)
class DeleteUser(Command[None]):
    """An administrator deletes someone else's account."""

    actor_id: str
    user_id: str


class AccountRemover:
    """Deletes an account together with everything every module stores about the user (GDPR)."""

    def __init__(self, users: UserRepository, transactions: TransactionManager, events: EventBus) -> None:
        self._users = users
        self._transactions = transactions
        self._events = events

    async def remove(self, user: User) -> None:
        if user.is_admin and await self._users.count_admins() <= 1:
            raise LastAdminError()
        async with self._transactions.transaction():
            await self._users.delete(user.id)
            await self._events.publish(UserDeleted(user_id=user.id, email=user.email))


class DeleteAccountHandler:
    def __init__(self, users: UserRepository, hasher: PasswordHasher, remover: AccountRemover) -> None:
        self._users = users
        self._hasher = hasher
        self._remover = remover

    async def handle(self, command: DeleteAccount) -> None:
        user = await self._users.find(command.user_id)
        if user is None:
            raise UserNotFoundError()
        if not await self._hasher.verify(command.password, user.password_hash):
            raise InvalidCurrentPasswordError()
        await self._remover.remove(user)


class DeleteUserHandler:
    def __init__(self, users: UserRepository, remover: AccountRemover) -> None:
        self._users = users
        self._remover = remover

    async def handle(self, command: DeleteUser) -> None:
        if command.actor_id == command.user_id:
            raise OwnAccountError()
        user = await self._users.find(command.user_id)
        if user is None:
            raise UserNotFoundError()
        await self._remover.remove(user)
