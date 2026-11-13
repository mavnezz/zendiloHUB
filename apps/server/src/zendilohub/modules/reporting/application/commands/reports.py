from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from zendilohub.core.bus.message import Command, Query
from zendilohub.core.domain.app_domain_error import ValidationError
from zendilohub.core.domain.clock import Clock

from ...domain.ports.repositories import Period, Report, ReportRepository, Tickets

DAYS_MAX = 366


class InvalidPeriodError(ValidationError):
    def __init__(self, field: str) -> None:
        super().__init__('invalid_period', f'Please check the period ({field})', {'field': field})


@dataclass(frozen=True, kw_only=True)
class Track(Command[None]):
    tenant_id: str
    ticket_id: str
    responded: bool = False
    breached: bool = False


class TrackHandler:
    def __init__(self, reports: ReportRepository, tickets: Tickets, clock: Clock) -> None:
        self._reports = reports
        self._tickets = tickets
        self._clock = clock

    async def handle(self, command: Track) -> None:
        facts = await self._tickets.facts(command.tenant_id, command.ticket_id)
        if facts is None:
            return
        now = self._clock.now()
        await self._reports.track(command.tenant_id, facts, now)
        if command.responded:
            await self._reports.responded(command.tenant_id, facts.id, now)
        if command.breached:
            await self._reports.breached(command.tenant_id, facts.id)


@dataclass(frozen=True, kw_only=True)
class GetReport(Query[Report]):
    """Tickets opened and closed from `start` to `end` (days in `timezone`, both included)."""

    tenant_id: str
    start: date
    end: date
    timezone: str = 'UTC'
    queue_id: str | None = None


class GetReportHandler:
    def __init__(self, reports: ReportRepository) -> None:
        self._reports = reports

    async def handle(self, query: GetReport) -> Report:
        try:
            zone = ZoneInfo(query.timezone)
        except ZoneInfoNotFoundError, ValueError:
            raise InvalidPeriodError('timezone') from None
        if query.end < query.start:
            raise InvalidPeriodError('end')
        if (query.end - query.start).days >= DAYS_MAX:
            raise InvalidPeriodError('start')
        return await self._reports.report(
            Period(
                tenant_id=query.tenant_id,
                start=datetime.combine(query.start, time.min, zone),
                end=datetime.combine(query.end + timedelta(days=1), time.min, zone),
                timezone=query.timezone,
                queue_id=query.queue_id,
            )
        )


@dataclass(frozen=True)
class ForgetTenant(Command[None]):
    tenant_id: str


class ForgetTenantHandler:
    def __init__(self, reports: ReportRepository) -> None:
        self._reports = reports

    async def handle(self, command: ForgetTenant) -> None:
        await self._reports.forget_tenant(command.tenant_id)
