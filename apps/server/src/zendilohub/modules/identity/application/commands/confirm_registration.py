from dataclasses import dataclass

from zendilohub.core.bus.message import Command
from zendilohub.core.domain.clock import Clock
from zendilohub.core.domain.id_generator import IdGenerator
from zendilohub.core.domain.transaction import TransactionManager
from zendilohub.core.events.event_bus import EventBus
from zendilohub.core.events.integration_events import UserRegistered

from ...domain.exceptions import InvalidTokenError
from ...domain.models.user import User
from ...domain.ports.registration_repository import RegistrationRepository
from ...domain.ports.token_service import TokenService
from ...domain.ports.user_repository import UserRepository
from ..services.session_starter import LoginResult, SessionStarter


@dataclass(frozen=True)
class ConfirmRegistration(Command[LoginResult]):
    token: str


class ConfirmRegistrationHandler:
    """Creates the account of a confirmed sign-up and logs the user in."""

    def __init__(
        self,
        users: UserRepository,
        registrations: RegistrationRepository,
        tokens: TokenService,
        sessions: SessionStarter,
        transactions: TransactionManager,
        events: EventBus,
        ids: IdGenerator,
        clock: Clock,
    ) -> None:
        self._users = users
        self._registrations = registrations
        self._tokens = tokens
        self._sessions = sessions
        self._transactions = transactions
        self._events = events
        self._ids = ids
        self._clock = clock

    async def handle(self, command: ConfirmRegistration) -> LoginResult:
        now = self._clock.now()
        registration = await self._registrations.find(self._tokens.id_of(command.token))
        if registration is None or registration.is_expired(now):
            raise InvalidTokenError()

        if await self._users.find_by_email(registration.email) is not None:
            # Another sign-up with this address was confirmed first.
            await self._registrations.delete_by_email(registration.email)
            raise InvalidTokenError()

        async with self._transactions.transaction():
            await self._registrations.delete_by_email(registration.email)
            user = User.from_registration(id=self._ids.new_id(), registration=registration, now=now)
            await self._users.save(user)
            await self._events.publish(UserRegistered(user_id=user.id, email=user.email))
            return await self._sessions.start(user)
