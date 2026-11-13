from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..exceptions import InvalidTenantNameError, InvalidTimezoneError

type TenantStatus = Literal['active', 'suspended']
type Locale = Literal['de', 'en']

LOCALES: tuple[Locale, ...] = ('de', 'en')
NAME_MAX_LENGTH = 100


def checked_name(raw: str) -> str:
    name = ' '.join(raw.split())
    if not 1 <= len(name) <= NAME_MAX_LENGTH:
        raise InvalidTenantNameError(NAME_MAX_LENGTH)
    return name


def checked_timezone(name: str) -> str:
    try:
        ZoneInfo(name)
    except ZoneInfoNotFoundError, ValueError:
        raise InvalidTimezoneError() from None
    return name


@dataclass(kw_only=True)
class Tenant:
    """An organization: one customer of the platform with its own phone system, agents and data."""

    id: str
    name: str
    status: TenantStatus
    """Suspended tenants keep their data, but nobody can use them (set by the platform's administrators)."""
    timezone: str
    """Business hours, reports and dates are in this time zone."""
    locale: Locale
    """The language of the e-mails the organization sends (invitations) and the default for announcements."""
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(cls, *, id: str, name: str, timezone: str, locale: Locale, now: datetime) -> Tenant:
        return cls(
            id=id,
            name=checked_name(name),
            status='active',
            timezone=checked_timezone(timezone),
            locale=locale,
            created_at=now,
            updated_at=now,
        )

    @property
    def is_active(self) -> bool:
        return self.status == 'active'

    def update(self, *, name: str | None, timezone: str | None, locale: Locale | None, now: datetime) -> None:
        if name is not None:
            self.name = checked_name(name)
        if timezone is not None:
            self.timezone = checked_timezone(timezone)
        if locale is not None:
            self.locale = locale
        self.updated_at = now

    def change_status(self, status: TenantStatus, now: datetime) -> None:
        self.status = status
        self.updated_at = now
