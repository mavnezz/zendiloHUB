from dataclasses import dataclass

from zendilohub.core.bus.message import Command
from zendilohub.core.domain.clock import Clock
from zendilohub.core.domain.transaction import TransactionManager

from ...domain.exceptions import InvalidTokenError
from ...domain.models.password_policy import check_password
from ...domain.ports.password_hasher import PasswordHasher
from ...domain.ports.password_reset_repository import PasswordResetRepository
from ...domain.ports.session_repository import SessionRepository
from ...domain.ports.token_service import TokenService
from ...domain.ports.user_repository import UserRepository
from ..services.session_starter import LoginResult, SessionStarter


@dataclass(frozen=True)
class ResetPassword(Command[LoginResult]):
    token: str
    password: str


class ResetPasswordHandler:
    """Sets a new password, ends every other session and logs the user in."""

    def __init__(
        self,
        users: UserRepository,
        resets: PasswordResetRepository,
        sessions: SessionRepository,
        hasher: PasswordHasher,
        tokens: TokenService,
        starter: SessionStarter,
        transactions: TransactionManager,
        clock: Clock,
    ) -> None:
        self._users = users
        self._resets = resets
        self._sessions = sessions
        self._hasher = hasher
        self._tokens = tokens
        self._starter = starter
        self._transactions = transactions
        self._clock = clock

    async def handle(self, command: ResetPassword) -> LoginResult:
        now = self._clock.now()
        reset = await self._resets.find(self._tokens.id_of(command.token))
        user = await self._users.find(reset.user_id) if reset and not reset.is_expired(now) else None
        if user is None:
            raise InvalidTokenError()
        check_password(command.password)
        password_hash = await self._hasher.hash(command.password)

        async with self._transactions.transaction():
            user.change_password(password_hash, now)
            await self._users.save(user)
            await self._resets.delete_for_user(user.id)
            await self._sessions.delete_for_user(user.id)
            return await self._starter.start(user)
