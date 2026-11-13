import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from zendilohub.core.domain.app_domain_error import NotFoundError, ValidationError

_TIME = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')
WEEKDAYS = ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')


class InvalidServiceError(ValidationError):
    def __init__(self, field: str) -> None:
        super().__init__('invalid_service', f'Please check the service level ({field})', {'field': field})


class ServiceNotFoundError(NotFoundError):
    def __init__(self) -> None:
        super().__init__('service_not_found', 'The service level or calendar does not exist')


@dataclass(kw_only=True)
class Calendar:
    """Business hours in a time zone, with holidays (like OTOBO's and Zammad's calendars)."""

    id: str
    tenant_id: str
    name: str
    timezone: str
    hours: dict[str, list[tuple[str, str]]]
    """By weekday (`mon` … `sun`): opening intervals, e.g. [('08:00', '12:00'), ('13:00', '17:00')]."""
    holidays: tuple[str, ...] = ()
    """Days off (ISO dates)."""
    created_at: datetime

    def check(self) -> None:
        self.name = ' '.join(self.name.split())
        if not 1 <= len(self.name) <= 80:
            raise InvalidServiceError('name')
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError, ValueError:
            raise InvalidServiceError('timezone') from None
        if set(self.hours) - set(WEEKDAYS):
            raise InvalidServiceError('hours')
        for intervals in self.hours.values():
            for start, end in intervals:
                if not (_TIME.match(start) and _TIME.match(end)) or start >= end:
                    raise InvalidServiceError('hours')
        if not any(self.hours.values()):
            raise InvalidServiceError('hours')
        try:
            self.holidays = tuple(sorted({date.fromisoformat(day).isoformat() for day in self.holidays}))
        except ValueError:
            raise InvalidServiceError('holidays') from None

    def add(self, start: datetime, minutes: int) -> datetime:
        """The moment `minutes` of business time after `start`."""
        zone = ZoneInfo(self.timezone)
        local = start.astimezone(zone)
        left = timedelta(minutes=minutes)
        day = local.date()
        for _ in range(3 * 366):
            if day.isoformat() not in self.holidays:
                for opening, closing in self.hours.get(WEEKDAYS[day.weekday()], []):
                    begin = datetime.combine(day, time.fromisoformat(opening), zone)
                    end = datetime.combine(day, time.fromisoformat(closing), zone)
                    begin = max(begin, local)
                    if begin >= end:
                        continue
                    if begin + left <= end:
                        return begin + left
                    left -= end - begin
            day += timedelta(days=1)
            local = datetime.combine(day, time.min, zone)
        return start + timedelta(minutes=minutes)


@dataclass(kw_only=True)
class Policy:
    """
    A service level: tickets of these queues and priorities (empty: all) get a first response and a solution within
    so many minutes, counted in a calendar's business hours (none: around the clock). The first one that fits counts.
    """

    id: str
    tenant_id: str
    name: str
    position: int
    active: bool
    queue_ids: tuple[str, ...]
    priorities: tuple[str, ...]
    first_response_minutes: int | None
    solution_minutes: int | None
    calendar_id: str | None
    created_at: datetime

    def check(self) -> None:
        self.name = ' '.join(self.name.split())
        if not 1 <= len(self.name) <= 80:
            raise InvalidServiceError('name')
        if any(priority not in ('low', 'normal', 'high', 'urgent') for priority in self.priorities):
            raise InvalidServiceError('priorities')
        for minutes, name in (
            (self.first_response_minutes, 'first_response_minutes'),
            (self.solution_minutes, 'solution_minutes'),
        ):
            if minutes is not None and not 1 <= minutes <= 60 * 24 * 365:
                raise InvalidServiceError(name)
        if self.first_response_minutes is None and self.solution_minutes is None:
            raise InvalidServiceError('first_response_minutes')

    def fits(self, queue_id: str, priority: str) -> bool:
        return (
            self.active
            and (not self.queue_ids or queue_id in self.queue_ids)
            and (not self.priorities or priority in self.priorities)
        )


@dataclass(kw_only=True)
class TicketClock:
    """A ticket's deadlines under its service level."""

    tenant_id: str
    ticket_id: str
    policy_id: str
    started_at: datetime
    first_response_due: datetime | None
    solution_due: datetime | None
    first_responded_at: datetime | None = None
    solved_at: datetime | None = None
    breached: set[str] = field(default_factory=set)
    """`first_response`, `solution`."""

    def due(self, now: datetime) -> list[str]:
        """What has come due without being met and was not reported yet."""
        late = []
        if self.first_response_due and not self.first_responded_at and self.first_response_due <= now:
            late.append('first_response')
        if self.solution_due and not self.solved_at and self.solution_due <= now:
            late.append('solution')
        return [kind for kind in late if kind not in self.breached]


def deadlines(policy: Policy, calendar: Calendar | None, start: datetime) -> tuple[datetime | None, datetime | None]:
    def at(minutes: int | None) -> datetime | None:
        if minutes is None:
            return None
        return calendar.add(start, minutes) if calendar else start + timedelta(minutes=minutes)

    return at(policy.first_response_minutes), at(policy.solution_minutes)
