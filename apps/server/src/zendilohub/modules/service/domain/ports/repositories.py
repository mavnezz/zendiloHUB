from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from zendilohub.core.domain.automation import TicketFacts

from ..models.sla import Calendar, Policy, TicketClock


class ServiceRepository(Protocol):
    async def calendars(self, tenant_id: str) -> Sequence[Calendar]: ...

    async def calendar(self, tenant_id: str, calendar_id: str) -> Calendar | None: ...

    async def save_calendar(self, calendar: Calendar) -> None: ...

    async def delete_calendar(self, tenant_id: str, calendar_id: str) -> None:
        """Policies that counted in it count around the clock."""
        ...

    async def policies(self, tenant_id: str) -> Sequence[Policy]:
        """In their order."""
        ...

    async def save_policy(self, policy: Policy) -> None: ...

    async def delete_policy(self, tenant_id: str, policy_id: str) -> None:
        """With the deadlines it set."""
        ...

    async def clock(self, tenant_id: str, ticket_id: str) -> TicketClock | None: ...

    async def save_clock(self, clock: TicketClock) -> None: ...

    async def delete_clock(self, tenant_id: str, ticket_id: str) -> None: ...

    async def running(self, now: datetime) -> Sequence[TicketClock]:
        """Clocks of every organization with a deadline passed and not yet reported."""
        ...

    async def escalations(self, tenant_id: str, until: datetime) -> Sequence[TicketClock]:
        """Clocks with an open deadline before `until` (passed or soon)."""
        ...

    async def forget_tenant(self, tenant_id: str) -> None: ...


class Tickets(Protocol):
    async def facts(self, tenant_id: str, ticket_id: str) -> TicketFacts | None: ...
