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
