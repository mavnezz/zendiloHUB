from typing import Annotated, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.http.access import Member, member_with
from zendilohub.core.http.audit import audited

from ...application.commands.numbering import GetNumbering, NumberingView, SaveNumbering
from ...domain.models.numbering import DATE_DIGITS, START_MAX, Numbering

Admin = Annotated[Member, member_with('tenant.manage', people_only=True)]


class TicketNumberingBody(BaseModel):
    model_config = ConfigDict(extra='forbid')

    format: Literal['increment', 'date'] = 'increment'
    """`increment`: 1001, 1002, …; `date`: the day and its counter, 202611140001."""
    start: int = Field(default=1001, ge=1, le=START_MAX)
    date_digits: int = Field(default=4, ge=DATE_DIGITS.start, le=DATE_DIGITS.stop - 1)
    checksum: bool = False
    prefix: str = Field(default='#', min_length=1, max_length=16)
    """Stands before the number in e-mail subjects: `[#1001]`, `[Ticket#1001]`."""


class TicketNumberingResponse(TicketNumberingBody):
    next_number: int
    next_tag: str
    """The next ticket's tag in e-mail subjects, e.g. `[Ticket#202611140001]`."""

    @classmethod
    def of(cls, view: NumberingView) -> TicketNumberingResponse:
        numbering = view.numbering
        return cls(
            format=numbering.format,
            start=numbering.start,
            date_digits=numbering.date_digits,
            checksum=numbering.checksum,
            prefix=numbering.prefix,
            next_number=view.next_number,
            next_tag=numbering.tag(view.next_number),
        )


def numbering_routes(bus: CommandBus) -> APIRouter:
    router = APIRouter(prefix='/tenants/{tenant_id}', tags=['tickets'])

    @router.get('/ticket-numbers')
    async def show(member: Admin) -> TicketNumberingResponse:
        """How the organization numbers its tickets, with the next number."""
        return TicketNumberingResponse.of(await bus.query(GetNumbering(member.tenant_id)))

    @router.put('/ticket-numbers', dependencies=[audited('ticket_numbers.changed')])
    async def save(body: TicketNumberingBody, member: Admin) -> TicketNumberingResponse:
        """Numbers already handed out stay; a new start must lie above the last number."""
        numbering = Numbering(tenant_id=member.tenant_id, **body.model_dump())
        return TicketNumberingResponse.of(await bus.execute(SaveNumbering(numbering)))

    return router
