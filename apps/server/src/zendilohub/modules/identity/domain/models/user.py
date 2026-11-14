from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from .registration import Registration

type Role = Literal['user', 'admin']
type Locale = Literal['de', 'en']

ROLES: tuple[Role, ...] = ('user', 'admin')
LOCALES: tuple[Locale, ...] = ('de', 'en')


@dataclass(kw_only=True)
class User:
    id: str
    email: str
    password_hash: str
    role: Role
    locale: Locale
    """The language of the e-mails the user gets."""
    email_verified_at: datetime
    created_at: datetime
    updated_at: datetime
    totp_secret: bytes | None = None
    """The sealed secret of the authenticator app while two-factor login is on."""
    totp_pending: bytes | None = None
    """The sealed secret of a setup that is not confirmed with a code yet."""
    totp_enabled_at: datetime | None = None
    totp_last_step: int = 0
    """The time step of the last accepted code: no code works twice."""
    recovery_codes: tuple[str, ...] = ()
    """SHA-256 hashes of the unused recovery codes."""

    @classmethod
    def from_registration(cls, *, id: str, registration: Registration, now: datetime) -> User:
        """The account of a sign-up whose e-mail address was just confirmed."""
        return cls(
            id=id,
            email=registration.email,
            password_hash=registration.password_hash,
            role='user',
            locale=registration.locale,
            email_verified_at=now,
            created_at=now,
            updated_at=now,
        )

    @classmethod
    def administrator(cls, *, id: str, email: str, password_hash: str, now: datetime, locale: Locale = 'en') -> User:
        """The first administrator (configuration or setup wizard): whoever runs the app vouches for the address."""
        return cls(
            id=id,
            email=email,
            password_hash=password_hash,
            role='admin',
            locale=locale,
            email_verified_at=now,
            created_at=now,
            updated_at=now,
        )

    @property
    def is_admin(self) -> bool:
        return self.role == 'admin'

    def change_password(self, password_hash: str, now: datetime) -> None:
        self.password_hash = password_hash
        self.updated_at = now

    def change_locale(self, locale: Locale, now: datetime) -> None:
        self.locale = locale
        self.updated_at = now

    def change_role(self, role: Role, now: datetime) -> None:
        self.role = role
        self.updated_at = now

    @property
    def two_factor(self) -> bool:
        return self.totp_enabled_at is not None and self.totp_secret is not None

    def begin_two_factor(self, sealed_secret: bytes, now: datetime) -> None:
        self.totp_pending = sealed_secret
        self.updated_at = now

    def enable_two_factor(self, *, step: int, recovery_codes: tuple[str, ...], now: datetime) -> None:
        """The pending secret becomes the one: the first code proved the app has it."""
        self.totp_secret = self.totp_pending
        self.totp_pending = None
        self.totp_enabled_at = now
        self.totp_last_step = step
        self.recovery_codes = recovery_codes
        self.updated_at = now

    def accept_step(self, step: int, now: datetime) -> None:
        self.totp_last_step = step
        self.updated_at = now

    def use_recovery_code(self, code_hash: str, now: datetime) -> bool:
        """Spends a recovery code; False if it is not one of the unused ones."""
        if code_hash not in self.recovery_codes:
            return False
        self.recovery_codes = tuple(code for code in self.recovery_codes if code != code_hash)
        self.updated_at = now
        return True

    def replace_recovery_codes(self, recovery_codes: tuple[str, ...], now: datetime) -> None:
        self.recovery_codes = recovery_codes
        self.updated_at = now

    def disable_two_factor(self, now: datetime) -> None:
        self.totp_secret = None
        self.totp_pending = None
        self.totp_enabled_at = None
        self.totp_last_step = 0
        self.recovery_codes = ()
        self.updated_at = now
