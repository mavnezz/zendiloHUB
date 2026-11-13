from dataclasses import dataclass, field

from zendilohub.core.bus.message import Command
from zendilohub.core.domain.clock import Clock
from zendilohub.core.domain.id_generator import IdGenerator
from zendilohub.core.domain.transaction import TransactionManager
from zendilohub.core.events.event_bus import EventBus
from zendilohub.core.events.integration_events import InstanceSetUp, UserRegistered

from ...domain.exceptions import InvalidSetupTokenError, SetupDoneError
from ...domain.models.email import normalize_email
from ...domain.models.password_policy import check_password
from ...domain.models.user import Locale, User
from ...domain.ports.password_hasher import PasswordHasher
from ...domain.ports.setup_token import SetupTokens
from ...domain.ports.user_repository import UserRepository
from ..services.session_starter import LoginResult, SessionStarter


@dataclass(frozen=True, kw_only=True)
class CompleteSetup(Command[LoginResult]):
    """The setup wizard of a self-hosted instance: the first administrator and the organization."""

    token: str = field(repr=False)
    email: str
    password: str = field(repr=False)
    organization_name: str
    timezone: str
    locale: Locale


class CompleteSetupHandler:
    """
    Creates the administrator and, through `InstanceSetUp` in the same transaction, the organization (tenancy
    checks its name and time zone, so a wrong one undoes the account too). Logs the administrator in.
    """

    def __init__(
        self,
        users: UserRepository,
        hasher: PasswordHasher,
        tokens: SetupTokens,
        starter: SessionStarter,
        transactions: TransactionManager,
        events: EventBus,
        ids: IdGenerator,
        clock: Clock,
        *,
        self_hosted: bool,
    ) -> None:
        self._self_hosted = self_hosted
        self._users = users
        self._hasher = hasher
        self._tokens = tokens
        self._starter = starter
        self._transactions = transactions
        self._events = events
        self._ids = ids
        self._clock = clock

    async def handle(self, command: CompleteSetup) -> LoginResult:
        if not self._self_hosted or await self._users.count_admins() > 0:
            raise SetupDoneError()
        if not self._tokens.matches(command.token):
            raise InvalidSetupTokenError()
        email = normalize_email(command.email)
        check_password(command.password)
        user = User.administrator(
            id=self._ids.new_id(),
            email=email,
            password_hash=await self._hasher.hash(command.password),
            now=self._clock.now(),
            locale=command.locale,
        )
        async with self._transactions.transaction():
            await self._users.save(user)
            await self._events.publish(UserRegistered(user_id=user.id, email=user.email))
            await self._events.publish(
                InstanceSetUp(
                    user_id=user.id,
                    email=user.email,
                    organization_name=command.organization_name,
                    timezone=command.timezone,
                    locale=command.locale,
                )
            )
        self._tokens.discard()
        return await self._starter.start(user)
