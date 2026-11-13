from dataclasses import dataclass
from datetime import datetime, timedelta

from .user import Locale

REGISTRATION_LIFETIME = timedelta(hours=48)


@dataclass(kw_only=True)
class Registration:
    """
    A sign-up waiting for its e-mail confirmation. The account only comes into being when
    the link of *this* registration is opened, with *this* registration's password: someone
    who signs up with another person's address can never end up knowing their password.
    The id is the hash of the token in the confirmation link.
    """

    id: str
    email: str
    password_hash: str
    locale: Locale
    created_at: datetime
    expires_at: datetime

    @classmethod
    def start(cls, *, id: str, email: str, password_hash: str, locale: Locale, now: datetime) -> Registration:
        return cls(
            id=id,
            email=email,
            password_hash=password_hash,
            locale=locale,
            created_at=now,
            expires_at=now + REGISTRATION_LIFETIME,
        )

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at

    def renew(self, id: str, now: datetime) -> Registration:
        """The same sign-up with a new confirmation link (the old one stops working)."""
        return Registration(
            id=id,
            email=self.email,
            password_hash=self.password_hash,
            locale=self.locale,
            created_at=self.created_at,
            expires_at=now + REGISTRATION_LIFETIME,
        )
