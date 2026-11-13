from dataclasses import dataclass

from zendilohub.core.bus.message import Command
from zendilohub.core.domain.clock import Clock
from zendilohub.core.domain.rate_limiter import RateLimiter

from ...domain.exceptions import InvalidEmailError
from ...domain.models.email import normalize_email
from ...domain.ports.account_notifier import AccountNotifier
from ...domain.ports.password_hasher import PasswordHasher
from ...domain.ports.registration_repository import RegistrationRepository
from ...domain.ports.token_service import TokenService
from ...domain.ports.user_repository import UserRepository
from ..services.limits import MAILS_PER_CLIENT, MAILS_PER_EMAIL, hit_all

# Signing up again and again with the same address must not make this expensive.
MAX_CANDIDATES = 5


@dataclass(frozen=True, kw_only=True)
class ResendConfirmation(Command[None]):
    """Sends a new confirmation link. Takes the password, so only the person who signed up gets a link."""

    email: str
    password: str
    client: str
    link_base: str


class ResendConfirmationHandler:
    def __init__(
        self,
        users: UserRepository,
        registrations: RegistrationRepository,
        hasher: PasswordHasher,
        tokens: TokenService,
        notifier: AccountNotifier,
        limiter: RateLimiter,
        clock: Clock,
    ) -> None:
        self._users = users
        self._registrations = registrations
        self._hasher = hasher
        self._tokens = tokens
        self._notifier = notifier
        self._limiter = limiter
        self._clock = clock

    async def handle(self, command: ResendConfirmation) -> None:
        try:
            email = normalize_email(command.email)
        except InvalidEmailError:
            return
        await hit_all(self._limiter, (MAILS_PER_EMAIL, email), (MAILS_PER_CLIENT, command.client))
        now = self._clock.now()
        for registration in list(await self._registrations.find_by_email(email))[:MAX_CANDIDATES]:
            if registration.is_expired(now) or not await self._hasher.verify(
                command.password, registration.password_hash
            ):
                continue
            user = await self._users.find_by_email(email)
            if user is not None:
                # The address has an account: its owner gets the hint, never a link for someone else's sign-up.
                await self._notifier.already_registered(user, f'{command.link_base}/login')
                return
            issued = self._tokens.issue()
            await self._registrations.delete(registration.id)
            renewed = registration.renew(issued.id, now)
            await self._registrations.save(renewed)
            await self._notifier.confirm_registration(renewed, f'{command.link_base}/verify-email?token={issued.token}')
            return
