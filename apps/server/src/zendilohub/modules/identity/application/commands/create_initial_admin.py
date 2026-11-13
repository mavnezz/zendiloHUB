from dataclasses import dataclass, field
from typing import Literal

from zendilohub.core.bus.message import Command
from zendilohub.core.domain.clock import Clock
from zendilohub.core.domain.id_generator import IdGenerator
from zendilohub.core.domain.transaction import TransactionManager
from zendilohub.core.events.event_bus import EventBus
from zendilohub.core.events.integration_events import UserRegistered

from ...domain.models.email import normalize_email
from ...domain.models.password_policy import check_password
from ...domain.models.user import User
from ...domain.ports.password_hasher import PasswordHasher
from ...domain.ports.user_repository import UserRepository

type InitialAdminOutcome = Literal['created', 'promoted', 'skipped']


@dataclass(frozen=True)
class CreateInitialAdmin(Command[InitialAdminOutcome]):
    """On start: the administrator from the configuration, as long as there is none.

    The last administrator can never be removed, so this happens once; afterwards the configured
    address and password are ignored (the password is changed in the app).
    """

    email: str
    password: str = field(repr=False)


class CreateInitialAdminHandler:
    def __init__(
        self,
        users: UserRepository,
        hasher: PasswordHasher,
        transactions: TransactionManager,
        events: EventBus,
        ids: IdGenerator,
        clock: Clock,
    ) -> None:
        self._users = users
        self._hasher = hasher
        self._transactions = transactions
        self._events = events
        self._ids = ids
        self._clock = clock

    async def handle(self, command: CreateInitialAdmin) -> InitialAdminOutcome:
        if await self._users.count_admins() > 0:
            return 'skipped'
        email = normalize_email(command.email)
        check_password(command.password)
        now = self._clock.now()

        existing = await self._users.find_by_email(email)
        if existing is not None:
            # Signed up before: the account becomes the administrator and keeps its own password.
            existing.change_role('admin', now)
            await self._users.save(existing)
            return 'promoted'

        user = User.administrator(
            id=self._ids.new_id(), email=email, password_hash=await self._hasher.hash(command.password), now=now
        )
        async with self._transactions.transaction():
            await self._users.save(user)
            await self._events.publish(UserRegistered(user_id=user.id, email=user.email))
        return 'created'
