from dataclasses import dataclass

from zendilohub.core.bus.message import Command
from zendilohub.core.domain.clock import Clock
from zendilohub.core.domain.rate_limiter import RateLimiter

from ...domain.exceptions import InvalidEmailError
from ...domain.models.email import normalize_email
from ...domain.models.password_reset import PasswordReset
from ...domain.ports.account_notifier import AccountNotifier
from ...domain.ports.password_reset_repository import PasswordResetRepository
from ...domain.ports.token_service import TokenService
from ...domain.ports.user_repository import UserRepository
from ..services.limits import MAILS_PER_CLIENT, MAILS_PER_EMAIL, hit_all


@dataclass(frozen=True, kw_only=True)
class RequestPasswordReset(Command[None]):
    """Sends a reset link if the address has an account; the answer is the same either way."""

    email: str
    client: str
    link_base: str


class RequestPasswordResetHandler:
    def __init__(
        self,
        users: UserRepository,
        resets: PasswordResetRepository,
        tokens: TokenService,
        notifier: AccountNotifier,
        limiter: RateLimiter,
        clock: Clock,
    ) -> None:
        self._users = users
        self._resets = resets
        self._tokens = tokens
        self._notifier = notifier
        self._limiter = limiter
        self._clock = clock

    async def handle(self, command: RequestPasswordReset) -> None:
        try:
            email = normalize_email(command.email)
        except InvalidEmailError:
            return
        await hit_all(self._limiter, (MAILS_PER_EMAIL, email), (MAILS_PER_CLIENT, command.client))
        user = await self._users.find_by_email(email)
        if user is None:
            return
        now = self._clock.now()
        await self._resets.delete_expired(now)
        # Only the newest link works.
        await self._resets.delete_for_user(user.id)
        issued = self._tokens.issue()
        await self._resets.save(PasswordReset.issue(id=issued.id, user_id=user.id, now=now))
        await self._notifier.reset_password(user, f'{command.link_base}/reset-password?token={issued.token}')
