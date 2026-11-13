from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta

from zendilohub.core.bus.message import Command, Query
from zendilohub.core.domain.clock import Clock
from zendilohub.core.domain.id_generator import IdGenerator
from zendilohub.core.events.event_bus import EventBus
from zendilohub.core.events.integration_events import SlaBreached

from ...domain.models.sla import Calendar, InvalidServiceError, Policy, ServiceNotFoundError, TicketClock, deadlines
from ...domain.ports.repositories import ServiceRepository, Tickets

SOON = timedelta(hours=1)


@dataclass(frozen=True, kw_only=True)
class SaveCalendar(Command[Calendar]):
    tenant_id: str
    name: str
    timezone: str
    hours: dict[str, list[tuple[str, str]]]
    holidays: tuple[str, ...] = ()
    calendar_id: str | None = None


class SaveCalendarHandler:
    def __init__(self, service: ServiceRepository, ids: IdGenerator, clock: Clock) -> None:
        self._service = service
        self._ids = ids
        self._clock = clock

    async def handle(self, command: SaveCalendar) -> Calendar:
        if (
            command.calendar_id is not None
            and await self._service.calendar(command.tenant_id, command.calendar_id) is None
        ):
            raise ServiceNotFoundError()
        calendar = Calendar(
            id=command.calendar_id or self._ids.new_id(),
            tenant_id=command.tenant_id,
            name=command.name,
            timezone=command.timezone,
            hours={day: list(intervals) for day, intervals in command.hours.items()},
            holidays=command.holidays,
            created_at=self._clock.now(),
        )
        calendar.check()
        await self._service.save_calendar(calendar)
        return calendar


@dataclass(frozen=True, kw_only=True)
class DeleteCalendar(Command[Calendar]):
    tenant_id: str
    calendar_id: str


class DeleteCalendarHandler:
    def __init__(self, service: ServiceRepository) -> None:
        self._service = service

    async def handle(self, command: DeleteCalendar) -> Calendar:
        found = await self._service.calendar(command.tenant_id, command.calendar_id)
        if found is None:
            raise ServiceNotFoundError()
        await self._service.delete_calendar(command.tenant_id, found.id)
        return found


@dataclass(frozen=True, kw_only=True)
class SavePolicy(Command[Policy]):
    tenant_id: str
    name: str
    active: bool
    queue_ids: tuple[str, ...]
    priorities: tuple[str, ...]
    first_response_minutes: int | None
    solution_minutes: int | None
    calendar_id: str | None
    policy_id: str | None = None


class SavePolicyHandler:
    def __init__(self, service: ServiceRepository, ids: IdGenerator, clock: Clock) -> None:
        self._service = service
        self._ids = ids
        self._clock = clock

    async def handle(self, command: SavePolicy) -> Policy:
        existing = list(await self._service.policies(command.tenant_id))
        found = next((each for each in existing if each.id == command.policy_id), None)
        if command.policy_id is not None and found is None:
            raise ServiceNotFoundError()
        if len(existing) >= 50 and found is None:
            raise InvalidServiceError('limit')
        if command.calendar_id and await self._service.calendar(command.tenant_id, command.calendar_id) is None:
            raise InvalidServiceError('calendar_id')
        policy = Policy(
            id=found.id if found else self._ids.new_id(),
            tenant_id=command.tenant_id,
            name=command.name,
            position=found.position if found else max((each.position for each in existing), default=0) + 1,
            active=command.active,
            queue_ids=command.queue_ids,
            priorities=command.priorities,
            first_response_minutes=command.first_response_minutes,
            solution_minutes=command.solution_minutes,
            calendar_id=command.calendar_id,
            created_at=found.created_at if found else self._clock.now(),
        )
        policy.check()
        await self._service.save_policy(policy)
        return policy


@dataclass(frozen=True, kw_only=True)
class DeletePolicy(Command[Policy]):
    tenant_id: str
    policy_id: str


class DeletePolicyHandler:
    def __init__(self, service: ServiceRepository) -> None:
        self._service = service

    async def handle(self, command: DeletePolicy) -> Policy:
        found = next(
            (each for each in await self._service.policies(command.tenant_id) if each.id == command.policy_id), None
        )
        if found is None:
            raise ServiceNotFoundError()
        await self._service.delete_policy(command.tenant_id, found.id)
        return found


@dataclass(frozen=True, kw_only=True)
class Track(Command[TicketClock | None]):
    """A ticket was created or changed: its service level (and deadlines from its start) is picked again."""

    tenant_id: str
    ticket_id: str
    responded: bool = False
    """The team replied to the customer."""


class TrackHandler:
    def __init__(self, service: ServiceRepository, tickets: Tickets, clock: Clock) -> None:
        self._service = service
        self._tickets = tickets
        self._clock = clock

    async def handle(self, command: Track) -> TicketClock | None:
        facts = await self._tickets.facts(command.tenant_id, command.ticket_id)
        current = await self._service.clock(command.tenant_id, command.ticket_id)
        if facts is None or facts.state == 'merged':
            if current:
                await self._service.delete_clock(command.tenant_id, command.ticket_id)
            return None
        policy = next(
            (
                each
                for each in await self._service.policies(command.tenant_id)
                if each.fits(facts.queue_id, facts.priority)
            ),
            None,
        )
        if policy is None:
            if current:
                await self._service.delete_clock(command.tenant_id, command.ticket_id)
            return None
        calendar = await self._service.calendar(command.tenant_id, policy.calendar_id) if policy.calendar_id else None
        start = current.started_at if current else facts.created_at
        first_due, solution_due = deadlines(policy, calendar, start)
        now = self._clock.now()
        clock = TicketClock(
            tenant_id=command.tenant_id,
            ticket_id=facts.id,
            policy_id=policy.id,
            started_at=start,
            first_response_due=first_due,
            solution_due=solution_due,
            first_responded_at=(current.first_responded_at if current else None)
            or (now if command.responded else None),
            solved_at=((current.solved_at if current else None) or now) if facts.state == 'closed' else None,
            breached=current.breached if current and current.policy_id == policy.id else set(),
        )
        await self._service.save_clock(clock)
        return clock


@dataclass(frozen=True)
class CheckDeadlines(Command[int]):
    """Reports every deadline that passed (a scheduled job); returns how many."""


class CheckDeadlinesHandler:
    def __init__(self, service: ServiceRepository, events: EventBus, clock: Clock) -> None:
        self._service = service
        self._events = events
        self._clock = clock

    async def handle(self, command: CheckDeadlines) -> int:
        now, reported = self._clock.now(), 0
        for clock in await self._service.running(now):
            for kind in clock.due(now):
                clock.breached.add(kind)
                await self._events.publish(SlaBreached(tenant_id=clock.tenant_id, ticket_id=clock.ticket_id, kind=kind))
                reported += 1
            await self._service.save_clock(clock)
        return reported


@dataclass(frozen=True)
class ServiceSetup:
    calendars: Sequence[Calendar]
    policies: Sequence[Policy]


@dataclass(frozen=True)
class GetSetup(Query[ServiceSetup]):
    tenant_id: str


class GetSetupHandler:
    def __init__(self, service: ServiceRepository) -> None:
        self._service = service

    async def handle(self, query: GetSetup) -> ServiceSetup:
        return ServiceSetup(
            await self._service.calendars(query.tenant_id), await self._service.policies(query.tenant_id)
        )


@dataclass(frozen=True)
class ClockOf(Query[TicketClock | None]):
    tenant_id: str
    ticket_id: str


class ClockOfHandler:
    def __init__(self, service: ServiceRepository) -> None:
        self._service = service

    async def handle(self, query: ClockOf) -> TicketClock | None:
        return await self._service.clock(query.tenant_id, query.ticket_id)


@dataclass(frozen=True)
class Escalations(Query[Sequence[TicketClock]]):
    """Open deadlines that passed or come within the hour."""

    tenant_id: str


class EscalationsHandler:
    def __init__(self, service: ServiceRepository, clock: Clock) -> None:
        self._service = service
        self._clock = clock

    async def handle(self, query: Escalations) -> Sequence[TicketClock]:
        return await self._service.escalations(query.tenant_id, self._clock.now() + SOON)


@dataclass(frozen=True)
class ForgetTenant(Command[None]):
    tenant_id: str


class ForgetTenantHandler:
    def __init__(self, service: ServiceRepository) -> None:
        self._service = service

    async def handle(self, command: ForgetTenant) -> None:
        await self._service.forget_tenant(command.tenant_id)
