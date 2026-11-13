from dataclasses import dataclass

from zendilohub.core.bus.message import Command
from zendilohub.core.domain.clock import Clock
from zendilohub.core.domain.rate_limiter import RateLimiter

from ...domain.exceptions import SignUpClosedError
from ...domain.models.email import normalize_email
from ...domain.models.password_policy import check_password
from ...domain.models.registration import Registration
from ...domain.models.user import Locale
from ...domain.ports.account_notifier import AccountNotifier
from ...domain.ports.password_hasher import PasswordHasher
from ...domain.ports.registration_repository import RegistrationRepository
from ...domain.ports.sign_up_policy import SignUpPolicy
from ...domain.ports.token_service import TokenService
from ...domain.ports.user_repository import UserRepository
from ..services.limits import MAILS_PER_CLIENT, MAILS_PER_EMAIL, hit_all


@dataclass(frozen=True, kw_only=True)
class Register(Command[None]):
    email: str
    password: str
    locale: Locale
    client: str
    """The client's IP address, for rate limiting."""
    link_base: str
    """The app's public URL; links in e-mails start with it."""


class RegisterHandler:
    """
    Starts a sign-up and sends the confirmation link. The answer is the same whether
    the address already has an account or not (that owner gets a hint by e-mail instead),
    so the sign-up form cannot be used to find out who has an account. On a self-hosted
    instance only invited addresses may sign up.
    """

    def __init__(
        self,
        users: UserRepository,
        registrations: RegistrationRepository,
        hasher: PasswordHasher,
        tokens: TokenService,
        notifier: AccountNotifier,
        limiter: RateLimiter,
        clock: Clock,
        policy: SignUpPolicy,
    ) -> None:
        self._policy = policy
        self._users = users
        self._registrations = registrations
        self._hasher = hasher
        self._tokens = tokens
        self._notifier = notifier
        self._limiter = limiter
        self._clock = clock

    async def handle(self, command: Register) -> None:
        email = normalize_email(command.email)
        check_password(command.password)
        if not await self._policy.allows(email):
            raise SignUpClosedError()
        await hit_all(self._limiter, (MAILS_PER_EMAIL, email), (MAILS_PER_CLIENT, command.client))

        password_hash = await self._hasher.hash(command.password)
        issued = self._tokens.issue()
        registration = Registration.start(
            id=issued.id, email=email, password_hash=password_hash, locale=command.locale, now=self._clock.now()
        )
        await self._registrations.delete_expired(self._clock.now())
        # Stored in both cases, so a login with this password answers the same either way (it can never be
        # confirmed for an address that has an account: its link is not sent, and confirming checks again).
        await self._registrations.save(registration)
        user = await self._users.find_by_email(email)
        if user is not None:
            await self._notifier.already_registered(user, f'{command.link_base}/login')
            return
        await self._notifier.confirm_registration(
            registration, f'{command.link_base}/verify-email?token={issued.token}'
        )
