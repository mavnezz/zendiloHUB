"""Two-factor login with an authenticator app (TOTP) and recovery codes."""

from dataclasses import dataclass

from zendilohub.core.bus.message import Command, Query
from zendilohub.core.domain.cipher import Cipher
from zendilohub.core.domain.clock import Clock
from zendilohub.core.domain.rate_limiter import RateLimiter

from ...domain.exceptions import (
    InvalidChallengeError,
    InvalidCurrentPasswordError,
    InvalidTwoFactorCodeError,
    OwnAccountError,
    TwoFactorNotStartedError,
    TwoFactorOffError,
    TwoFactorOnError,
    UserNotFoundError,
)
from ...domain.models import totp
from ...domain.models.user import User
from ...domain.ports.login_challenge_repository import LoginChallengeRepository
from ...domain.ports.password_hasher import PasswordHasher
from ...domain.ports.session_repository import SessionRepository
from ...domain.ports.token_service import TokenService
from ...domain.ports.user_repository import UserRepository
from ..services.limits import TWO_FACTOR_FAILURES_PER_USER, check_all, hit_all
from ..services.session_starter import LoginResult, SessionStarter


def _context(user_id: str) -> str:
    return f'user:{user_id}:totp'


@dataclass(frozen=True)
class TwoFactorStatus:
    enabled: bool
    recovery_codes_left: int


@dataclass(frozen=True)
class TwoFactorSetup:
    secret: str
    """For typing into the app by hand."""
    uri: str
    """otpauth:// for the QR code."""


@dataclass(frozen=True)
class GetTwoFactorStatus(Query[TwoFactorStatus]):
    user_id: str


@dataclass(frozen=True, kw_only=True)
class CompleteTwoFactorLogin(Command[LoginResult]):
    challenge: str
    code: str
    """A code of the app or one of the recovery codes."""


@dataclass(frozen=True, kw_only=True)
class BeginTwoFactorSetup(Command[TwoFactorSetup]):
    user_id: str
    password: str


@dataclass(frozen=True, kw_only=True)
class EnableTwoFactor(Command[tuple[str, ...]]):
    """Confirms the setup with a code of the app; returns the recovery codes (shown once)."""

    user_id: str
    session_id: str
    code: str


@dataclass(frozen=True, kw_only=True)
class RegenerateRecoveryCodes(Command[tuple[str, ...]]):
    user_id: str
    password: str


@dataclass(frozen=True, kw_only=True)
class DisableTwoFactor(Command[None]):
    user_id: str
    password: str


@dataclass(frozen=True, kw_only=True)
class ResetTwoFactor(Command[None]):
    """An administrator turns two-factor login off for someone who lost the phone and the recovery codes."""

    actor_id: str
    user_id: str


class TwoFactor:
    """What the handlers share: the user, the password check, the secret and the code check."""

    def __init__(
        self,
        users: UserRepository,
        hasher: PasswordHasher,
        cipher: Cipher,
        limiter: RateLimiter,
        clock: Clock,
    ) -> None:
        self.users = users
        self.hasher = hasher
        self.cipher = cipher
        self.limiter = limiter
        self.clock = clock

    async def user(self, user_id: str) -> User:
        user = await self.users.find(user_id)
        if user is None:
            raise UserNotFoundError()
        return user

    async def user_with_password(self, user_id: str, password: str) -> User:
        user = await self.user(user_id)
        if not await self.hasher.verify(password, user.password_hash):
            raise InvalidCurrentPasswordError()
        return user

    def secret(self, user: User, sealed: bytes | None) -> str | None:
        return self.cipher.open(sealed, context=_context(user.id)) if sealed else None

    async def check_code(self, user: User, secret: str | None, code: str, *, recovery: bool) -> None:
        """Accepts a fresh code of the app (or, with `recovery`, an unused recovery code); counts wrong ones."""
        limit = ((TWO_FACTOR_FAILURES_PER_USER, user.id),)
        await check_all(self.limiter, *limit)
        now = self.clock.now()
        step = totp.matching_step(secret, code, now, after=user.totp_last_step) if secret else None
        if step is not None:
            user.accept_step(step, now)
        elif not (recovery and user.use_recovery_code(totp.hash_recovery_code(code), now)):
            await hit_all(self.limiter, *limit)
            raise InvalidTwoFactorCodeError()
        await self.limiter.reset(TWO_FACTOR_FAILURES_PER_USER, user.id)


def _new_codes() -> tuple[list[str], tuple[str, ...]]:
    codes = totp.new_recovery_codes()
    return codes, tuple(totp.hash_recovery_code(code) for code in codes)


class GetTwoFactorStatusHandler:
    def __init__(self, two_factor: TwoFactor) -> None:
        self._two_factor = two_factor

    async def handle(self, query: GetTwoFactorStatus) -> TwoFactorStatus:
        user = await self._two_factor.user(query.user_id)
        return TwoFactorStatus(user.two_factor, len(user.recovery_codes) if user.two_factor else 0)


class CompleteTwoFactorLoginHandler:
    def __init__(
        self,
        two_factor: TwoFactor,
        challenges: LoginChallengeRepository,
        tokens: TokenService,
        starter: SessionStarter,
    ) -> None:
        self._two_factor = two_factor
        self._challenges = challenges
        self._tokens = tokens
        self._starter = starter

    async def handle(self, command: CompleteTwoFactorLogin) -> LoginResult:
        challenge = await self._challenges.find(self._tokens.id_of(command.challenge))
        if challenge is None:
            raise InvalidChallengeError()
        if challenge.is_expired(self._two_factor.clock.now()):
            await self._challenges.delete(challenge.id)
            raise InvalidChallengeError()
        user = await self._two_factor.users.find(challenge.user_id)
        if user is None or not user.two_factor:
            # Turned off in the meantime (by the user or an administrator): the password alone is a fresh login.
            await self._challenges.delete(challenge.id)
            raise InvalidChallengeError()
        try:
            await self._two_factor.check_code(
                user, self._two_factor.secret(user, user.totp_secret), command.code, recovery=True
            )
        except InvalidTwoFactorCodeError:
            if challenge.fail():
                await self._challenges.save(challenge)
            else:
                await self._challenges.delete(challenge.id)
            raise
        await self._two_factor.users.save(user)
        await self._challenges.delete(challenge.id)
        return await self._starter.start_session(user)


class BeginTwoFactorSetupHandler:
    def __init__(self, two_factor: TwoFactor) -> None:
        self._two_factor = two_factor

    async def handle(self, command: BeginTwoFactorSetup) -> TwoFactorSetup:
        user = await self._two_factor.user_with_password(command.user_id, command.password)
        if user.two_factor:
            raise TwoFactorOnError()
        secret = totp.new_secret()
        user.begin_two_factor(
            self._two_factor.cipher.seal(secret, context=_context(user.id)), self._two_factor.clock.now()
        )
        await self._two_factor.users.save(user)
        return TwoFactorSetup(secret, totp.provisioning_uri(secret, user.email))


class EnableTwoFactorHandler:
    def __init__(self, two_factor: TwoFactor, sessions: SessionRepository) -> None:
        self._two_factor = two_factor
        self._sessions = sessions

    async def handle(self, command: EnableTwoFactor) -> tuple[str, ...]:
        user = await self._two_factor.user(command.user_id)
        if user.two_factor:
            raise TwoFactorOnError()
        secret = self._two_factor.secret(user, user.totp_pending)
        if secret is None:
            raise TwoFactorNotStartedError()
        await self._two_factor.check_code(user, secret, command.code, recovery=False)
        codes, hashes = _new_codes()
        user.enable_two_factor(step=user.totp_last_step, recovery_codes=hashes, now=self._two_factor.clock.now())
        await self._two_factor.users.save(user)
        await self._sessions.delete_for_user(user.id, except_session=command.session_id)
        return tuple(codes)


class RegenerateRecoveryCodesHandler:
    def __init__(self, two_factor: TwoFactor) -> None:
        self._two_factor = two_factor

    async def handle(self, command: RegenerateRecoveryCodes) -> tuple[str, ...]:
        user = await self._two_factor.user_with_password(command.user_id, command.password)
        if not user.two_factor:
            raise TwoFactorOffError()
        codes, hashes = _new_codes()
        user.replace_recovery_codes(hashes, self._two_factor.clock.now())
        await self._two_factor.users.save(user)
        return tuple(codes)


class DisableTwoFactorHandler:
    def __init__(self, two_factor: TwoFactor, challenges: LoginChallengeRepository) -> None:
        self._two_factor = two_factor
        self._challenges = challenges

    async def handle(self, command: DisableTwoFactor) -> None:
        user = await self._two_factor.user_with_password(command.user_id, command.password)
        if not user.two_factor:
            raise TwoFactorOffError()
        user.disable_two_factor(self._two_factor.clock.now())
        await self._two_factor.users.save(user)
        await self._challenges.delete_for_user(user.id)


class ResetTwoFactorHandler:
    def __init__(
        self, two_factor: TwoFactor, sessions: SessionRepository, challenges: LoginChallengeRepository
    ) -> None:
        self._two_factor = two_factor
        self._sessions = sessions
        self._challenges = challenges

    async def handle(self, command: ResetTwoFactor) -> None:
        if command.actor_id == command.user_id:
            raise OwnAccountError()
        user = await self._two_factor.user(command.user_id)
        if not user.two_factor:
            raise TwoFactorOffError()
        user.disable_two_factor(self._two_factor.clock.now())
        await self._two_factor.users.save(user)
        await self._challenges.delete_for_user(user.id)
        await self._sessions.delete_for_user(user.id)
