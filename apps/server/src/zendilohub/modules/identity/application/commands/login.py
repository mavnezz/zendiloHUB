from dataclasses import dataclass

from zendilohub.core.bus.message import Command
from zendilohub.core.domain.clock import Clock
from zendilohub.core.domain.rate_limiter import RateLimiter

from ...domain.exceptions import EmailNotVerifiedError, InvalidCredentialsError, InvalidEmailError
from ...domain.models.email import normalize_email
from ...domain.ports.password_hasher import PasswordHasher
from ...domain.ports.registration_repository import RegistrationRepository
from ...domain.ports.user_repository import UserRepository
from ..services.limits import LOGIN_FAILURES_PER_CLIENT, LOGIN_FAILURES_PER_EMAIL, check_all, hit_all
from ..services.session_starter import LoginResult, SessionStarter

MAX_PENDING_CHECKS = 3


@dataclass(frozen=True, kw_only=True)
class Login(Command[LoginResult]):
    email: str
    password: str
    client: str


class LoginHandler:
    def __init__(
        self,
        users: UserRepository,
        registrations: RegistrationRepository,
        hasher: PasswordHasher,
        sessions: SessionStarter,
        limiter: RateLimiter,
        clock: Clock,
    ) -> None:
        self._users = users
        self._registrations = registrations
        self._hasher = hasher
        self._sessions = sessions
        self._limiter = limiter
        self._clock = clock

    async def handle(self, command: Login) -> LoginResult:
        try:
            email = normalize_email(command.email)
        except InvalidEmailError:
            raise InvalidCredentialsError() from None
        limits = ((LOGIN_FAILURES_PER_EMAIL, email), (LOGIN_FAILURES_PER_CLIENT, command.client))
        await check_all(self._limiter, *limits)

        user = await self._users.find_by_email(email)
        if user is None:
            # Hash anyway, so the response time does not reveal which addresses have an account.
            await self._hasher.hash(command.password)
        if user is None or not await self._hasher.verify(command.password, user.password_hash):
            # Checked whether or not the address has an account, so the answer does not tell that either.
            if await self._matches_pending_sign_up(email, command.password):
                raise EmailNotVerifiedError()
            await hit_all(self._limiter, *limits)
            raise InvalidCredentialsError()

        await self._limiter.reset(LOGIN_FAILURES_PER_EMAIL, email)
        if self._hasher.needs_rehash(user.password_hash):
            user.change_password(await self._hasher.hash(command.password), self._clock.now())
            await self._users.save(user)
        return await self._sessions.start(user)

    async def _matches_pending_sign_up(self, email: str, password: str) -> bool:
        """Knowing the password of a sign-up proves it is theirs; then telling them to confirm it leaks nothing."""
        now = self._clock.now()
        for registration in list(await self._registrations.find_by_email(email))[:MAX_PENDING_CHECKS]:
            if not registration.is_expired(now) and await self._hasher.verify(password, registration.password_hash):
                return True
        return False
