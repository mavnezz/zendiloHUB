from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.http.access import CurrentMember, Member, member_with
from zendilohub.core.http.audit import audited, note_audit
from zendilohub.core.http.ids import Id

from ...application.commands.service import (
    ClockOf,
    DeleteCalendar,
    DeletePolicy,
    Escalations,
    GetSetup,
    SaveCalendar,
    SavePolicy,
)
from ...domain.models.sla import Calendar, Policy, TicketClock

Admin = Annotated[Member, member_with('service.manage')]
type Weekday = Literal['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class CalendarRequest(Strict):
    name: str = Field(max_length=80)
    timezone: str = Field(default='Europe/Berlin', max_length=64)
    hours: dict[Weekday, list[tuple[str, str]]]
    """Opening intervals per weekday, e.g. {"mon": [["08:00", "17:00"]]}."""
    holidays: list[str] = Field(default_factory=list, max_length=200)


class CalendarResponse(BaseModel):
    id: str
    name: str
    timezone: str
    hours: dict[str, list[tuple[str, str]]]
    holidays: list[str]

    @classmethod
    def of(cls, calendar: Calendar) -> CalendarResponse:
        return cls(
            id=calendar.id,
            name=calendar.name,
            timezone=calendar.timezone,
            hours=calendar.hours,
            holidays=list(calendar.holidays),
        )


class PolicyRequest(Strict):
    name: str = Field(max_length=80)
    active: bool = True
    queue_ids: list[Id] = Field(default_factory=list, max_length=200)
    """Empty: every queue."""
    priorities: list[Literal['low', 'normal', 'high', 'urgent']] = Field(default_factory=list)
    """Empty: every priority."""
    first_response_minutes: int | None = Field(default=None, ge=1)
    solution_minutes: int | None = Field(default=None, ge=1)
    calendar_id: Id | None = None
    """Count in this calendar's business hours; none: around the clock."""


class PolicyResponse(BaseModel):
    id: str
    name: str
    position: int
    active: bool
    queue_ids: list[str]
    priorities: list[str]
    first_response_minutes: int | None
    solution_minutes: int | None
    calendar_id: str | None

    @classmethod
    def of(cls, policy: Policy) -> PolicyResponse:
        return cls(
            id=policy.id,
            name=policy.name,
            position=policy.position,
            active=policy.active,
            queue_ids=list(policy.queue_ids),
            priorities=list(policy.priorities),
            first_response_minutes=policy.first_response_minutes,
            solution_minutes=policy.solution_minutes,
            calendar_id=policy.calendar_id,
        )


class SetupResponse(BaseModel):
    calendars: list[CalendarResponse]
    policies: list[PolicyResponse]


class ClockResponse(BaseModel):
    ticket_id: str
    policy_id: str
    first_response_due: datetime | None
    solution_due: datetime | None
    first_responded_at: datetime | None
    solved_at: datetime | None
    breached: list[str]

    @classmethod
    def of(cls, clock: TicketClock) -> ClockResponse:
        return cls(
            ticket_id=clock.ticket_id,
            policy_id=clock.policy_id,
            first_response_due=clock.first_response_due,
            solution_due=clock.solution_due,
            first_responded_at=clock.first_responded_at,
            solved_at=clock.solved_at,
            breached=sorted(clock.breached),
        )


def service_routes(bus: CommandBus) -> APIRouter:
    """Service levels: business hours, response and solution times, and the tickets about to miss them."""
    router = APIRouter(prefix='/tenants/{tenant_id}', tags=['service'])

    @router.get('/service-levels')
    async def setup(member: CurrentMember) -> SetupResponse:
        found = await bus.query(GetSetup(member.tenant_id))
        return SetupResponse(
            calendars=[CalendarResponse.of(each) for each in found.calendars],
            policies=[PolicyResponse.of(each) for each in found.policies],
        )

    @router.post('/service-calendars', status_code=201, dependencies=[audited('service_calendar.created')])
    async def create_calendar(body: CalendarRequest, request: Request, member: Admin) -> CalendarResponse:
        calendar = await bus.execute(
            SaveCalendar(
                tenant_id=member.tenant_id,
                name=body.name,
                timezone=body.timezone,
                hours={str(day): intervals for day, intervals in body.hours.items()},
                holidays=tuple(body.holidays),
            )
        )
        note_audit(request, target=calendar.name)
        return CalendarResponse.of(calendar)

    @router.patch('/service-calendars/{calendar_id}', dependencies=[audited('service_calendar.updated')])
    async def update_calendar(
        calendar_id: Id, body: CalendarRequest, request: Request, member: Admin
    ) -> CalendarResponse:
        calendar = await bus.execute(
            SaveCalendar(
                tenant_id=member.tenant_id,
                name=body.name,
                timezone=body.timezone,
                hours={str(day): intervals for day, intervals in body.hours.items()},
                holidays=tuple(body.holidays),
                calendar_id=calendar_id,
            )
        )
        note_audit(request, target=calendar.name)
        return CalendarResponse.of(calendar)

    @router.delete(
        '/service-calendars/{calendar_id}',
        status_code=204,
        response_class=Response,
        dependencies=[audited('service_calendar.deleted')],
    )
    async def delete_calendar(calendar_id: Id, request: Request, member: Admin) -> None:
        calendar = await bus.execute(DeleteCalendar(tenant_id=member.tenant_id, calendar_id=calendar_id))
        note_audit(request, target=calendar.name)

    @router.post('/service-policies', status_code=201, dependencies=[audited('service_policy.created')])
    async def create_policy(body: PolicyRequest, request: Request, member: Admin) -> PolicyResponse:
        policy = await bus.execute(_policy(body, member.tenant_id, None))
        note_audit(request, target=policy.name)
        return PolicyResponse.of(policy)

    @router.patch('/service-policies/{policy_id}', dependencies=[audited('service_policy.updated')])
    async def update_policy(policy_id: Id, body: PolicyRequest, request: Request, member: Admin) -> PolicyResponse:
        policy = await bus.execute(_policy(body, member.tenant_id, policy_id))
        note_audit(request, target=policy.name)
        return PolicyResponse.of(policy)

    @router.delete(
        '/service-policies/{policy_id}',
        status_code=204,
        response_class=Response,
        dependencies=[audited('service_policy.deleted')],
    )
    async def delete_policy(policy_id: Id, request: Request, member: Admin) -> None:
        policy = await bus.execute(DeletePolicy(tenant_id=member.tenant_id, policy_id=policy_id))
        note_audit(request, target=policy.name)

    @router.get('/tickets/{ticket_id}/service-level')
    async def clock(ticket_id: Id, member: CurrentMember) -> ClockResponse | None:
        """The ticket's deadlines (null without a service level)."""
        found = await bus.query(ClockOf(member.tenant_id, ticket_id))
        return ClockResponse.of(found) if found else None

    @router.get('/escalations')
    async def escalations(member: CurrentMember) -> list[ClockResponse]:
        """Open deadlines that passed or come within the hour, soonest first (ids only: the ticket list shows them)."""
        return [ClockResponse.of(each) for each in await bus.query(Escalations(member.tenant_id))]

    return router


def _policy(body: PolicyRequest, tenant_id: str, policy_id: str | None) -> SavePolicy:
    return SavePolicy(
        tenant_id=tenant_id,
        name=body.name,
        active=body.active,
        queue_ids=tuple(body.queue_ids),
        priorities=tuple(body.priorities),
        first_response_minutes=body.first_response_minutes,
        solution_minutes=body.solution_minutes,
        calendar_id=body.calendar_id,
        policy_id=policy_id,
    )
