from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol

from zendilohub.core.domain.automation import TicketFacts


@dataclass(frozen=True, kw_only=True)
class Period:
    tenant_id: str
    start: datetime
    end: datetime
    timezone: str
    queue_id: str | None = None


@dataclass(frozen=True)
class Day:
    day: date
    created: int
    closed: int


@dataclass(frozen=True)
class Group:
    key: str | None
    created: int
    closed: int
    open: int


@dataclass(frozen=True, kw_only=True)
class Report:
    created: int
    closed: int
    open_now: int
    unassigned_now: int
    first_response_median: float | None
    """Minutes, of the tickets opened in the period that got an answer."""
    first_response_average: float | None
    resolution_median: float | None
    """Minutes from opening to closing, of the tickets closed in the period."""
    breached: int
    """Tickets opened in the period that missed a service level."""
    reopened: int
    days: Sequence[Day] = field(default_factory=list)
    queues: Sequence[Group] = field(default_factory=list)
    owners: Sequence[Group] = field(default_factory=list)
    channels: Sequence[Group] = field(default_factory=list)


class ReportRepository(Protocol):
    async def track(self, tenant_id: str, facts: TicketFacts, now: datetime) -> None:
        """Keeps the ticket's line up to date (closing, reopening)."""
        ...

    async def responded(self, tenant_id: str, ticket_id: str, at: datetime) -> None:
        """The first answer to the customer (later ones change nothing)."""
        ...

    async def breached(self, tenant_id: str, ticket_id: str) -> None: ...

    async def report(self, period: Period) -> Report: ...

    async def forget_tenant(self, tenant_id: str) -> None: ...


class Tickets(Protocol):
    async def facts(self, tenant_id: str, ticket_id: str) -> TicketFacts | None: ...
