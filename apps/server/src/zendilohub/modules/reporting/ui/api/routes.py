from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.http.access import Member, member_with
from zendilohub.core.http.ids import Id

from ...application.commands.reports import GetReport
from ...domain.ports.repositories import Report

Viewer = Annotated[Member, member_with('reports.view')]


class DayResponse(BaseModel):
    day: date
    created: int
    closed: int


class GroupResponse(BaseModel):
    key: str | None
    """A queue id, a member's user id (null: nobody) or a channel."""
    created: int
    closed: int
    open: int


class ReportResponse(BaseModel):
    created: int
    closed: int
    open_now: int
    unassigned_now: int
    first_response_median: float | None
    """Minutes."""
    first_response_average: float | None
    resolution_median: float | None
    breached: int
    reopened: int
    days: list[DayResponse]
    queues: list[GroupResponse]
    owners: list[GroupResponse]
    channels: list[GroupResponse]

    @classmethod
    def of(cls, report: Report) -> ReportResponse:
        return cls(
            created=report.created,
            closed=report.closed,
            open_now=report.open_now,
            unassigned_now=report.unassigned_now,
            first_response_median=report.first_response_median,
            first_response_average=report.first_response_average,
            resolution_median=report.resolution_median,
            breached=report.breached,
            reopened=report.reopened,
            days=[DayResponse(day=each.day, created=each.created, closed=each.closed) for each in report.days],
            queues=[GroupResponse(**vars(each)) for each in report.queues],
            owners=[GroupResponse(**vars(each)) for each in report.owners],
            channels=[GroupResponse(**vars(each)) for each in report.channels],
        )


def report_routes(bus: CommandBus) -> APIRouter:
    router = APIRouter(prefix='/tenants/{tenant_id}', tags=['reporting'])

    @router.get('/reports')
    async def report(
        member: Viewer,
        start: date,
        end: date,
        timezone: Annotated[str, Query(max_length=64)] = 'UTC',
        queue_id: Annotated[Id | None, Query()] = None,
    ) -> ReportResponse:
        """Key figures of the tickets from `start` to `end` (days in `timezone`), for every queue or one."""
        found = await bus.query(
            GetReport(tenant_id=member.tenant_id, start=start, end=end, timezone=timezone, queue_id=queue_id)
        )
        return ReportResponse.of(found)

    return router
