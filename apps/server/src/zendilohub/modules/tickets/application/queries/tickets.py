from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from zendilohub.core.bus.message import Query
from zendilohub.core.domain.queue_rights import QueueRight

from ...domain.exceptions import TicketNotFoundError
from ...domain.models.actor import Actor
from ...domain.models.history import HistoryEntry
from ...domain.models.link import Link
from ...domain.models.message import Message
from ...domain.models.ticket import Priority, Ticket, TicketState
from ...domain.models.time_entry import TimeEntry
from ...domain.models.views import TicketFilter, TicketSort, TicketView
from ...domain.ports.repositories import (
    LinkRepository,
    MessageRepository,
    TimeRepository,
    WatcherRepository,
)
from ...domain.ports.services import CustomerDirectory
from ..services.desk import Desk


@dataclass(frozen=True)
class TicketWithRights:
    ticket: Ticket
    rights: frozenset[QueueRight]


@dataclass(frozen=True)
class TicketList:
    items: Sequence[TicketWithRights]
    total: int


@dataclass(frozen=True, kw_only=True)
class SearchTickets(Query[TicketList]):
    """A view of the inbox, narrowed by filters; only tickets in queues the actor may see."""

    tenant_id: str
    actor: Actor
    view: TicketView = 'open'
    queue_id: str | None = None
    state: TicketState | None = None
    priority: Priority | None = None
    owner_id: str | None = None
    customer_id: str | None = None
    company_id: str | None = None
    ticket_ids: tuple[str, ...] | None = None
    tag: str | None = None
    query: str = ''
    sort: TicketSort = 'updated'
    descending: bool = True
    offset: int = 0
    limit: int = 50


class SearchTicketsHandler:
    def __init__(self, desk: Desk, customers: CustomerDirectory) -> None:
        self._desk = desk
        self._customers = customers

    async def handle(self, query: SearchTickets) -> TicketList:
        desk = self._desk
        visible = await desk.rights.visible(query.tenant_id, query.actor)
        customers: tuple[str, ...] | None = None
        if query.customer_id is not None:
            customers = (query.customer_id,)
        if query.company_id is not None:
            customers = tuple(await self._customers.of_company(query.tenant_id, query.company_id))
        page = await desk.tickets.search(
            TicketFilter(
                tenant_id=query.tenant_id,
                queue_ids=tuple(visible),
                user_id=query.actor.user_id,
                now=desk.clock.now(),
                view=query.view,
                queue_id=query.queue_id,
                state=query.state,
                priority=query.priority,
                owner_id=query.owner_id,
                customer_ids=customers,
                ticket_ids=query.ticket_ids,
                tag=query.tag.lower() if query.tag else None,
                query=query.query.strip(),
                sort=query.sort,
                descending=query.descending,
                offset=query.offset,
                limit=query.limit,
            )
        )
        return TicketList([TicketWithRights(each, visible[each.queue_id]) for each in page.items], page.total)


@dataclass(frozen=True, kw_only=True)
class CountTickets(Query[Mapping[TicketView, int]]):
    """How many tickets each view of the inbox has, for the navigation."""

    tenant_id: str
    actor: Actor


class CountTicketsHandler:
    def __init__(self, desk: Desk) -> None:
        self._desk = desk

    async def handle(self, query: CountTickets) -> Mapping[TicketView, int]:
        visible = await self._desk.rights.visible(query.tenant_id, query.actor)
        return await self._desk.tickets.counts(
            TicketFilter(
                tenant_id=query.tenant_id,
                queue_ids=tuple(visible),
                user_id=query.actor.user_id,
                now=self._desk.clock.now(),
            )
        )


@dataclass(frozen=True)
class LinkedTicket:
    link: Link
    ticket: Ticket


@dataclass(frozen=True)
class TicketDetail:
    ticket: Ticket
    rights: frozenset[QueueRight]
    watchers: Sequence[str]
    links: Sequence[LinkedTicket]
    """Only those the actor may see."""
    time_minutes: int
    merged_into: Ticket | None


@dataclass(frozen=True, kw_only=True)
class GetTicket(Query[TicketDetail]):
    tenant_id: str
    actor: Actor
    ticket_id: str


class GetTicketHandler:
    def __init__(self, desk: Desk, watchers: WatcherRepository, links: LinkRepository, times: TimeRepository) -> None:
        self._desk = desk
        self._watchers = watchers
        self._links = links
        self._times = times

    async def handle(self, query: GetTicket) -> TicketDetail:
        desk = self._desk
        ticket, rights = await desk.load(query.tenant_id, query.actor, query.ticket_id)
        visible = await desk.rights.visible(query.tenant_id, query.actor)
        links = await self._links.of_ticket(ticket.tenant_id, ticket.id)
        others = {
            other.id: other
            for other in await desk.tickets.find_many(ticket.tenant_id, [link.other_id for link in links])
            if other.queue_id in visible
        }
        merged_into = (
            await desk.tickets.find(ticket.tenant_id, ticket.merged_into_id) if ticket.merged_into_id else None
        )
        return TicketDetail(
            ticket=ticket,
            rights=rights,
            watchers=await self._watchers.of_ticket(ticket.tenant_id, ticket.id),
            links=[LinkedTicket(link, others[link.other_id]) for link in links if link.other_id in others],
            time_minutes=sum(entry.minutes for entry in await self._times.of_ticket(ticket.tenant_id, ticket.id)),
            merged_into=merged_into if merged_into and merged_into.queue_id in visible else None,
        )


@dataclass(frozen=True, kw_only=True)
class FindTicketByNumber(Query[Ticket]):
    tenant_id: str
    actor: Actor
    number: int


class FindTicketByNumberHandler:
    def __init__(self, desk: Desk) -> None:
        self._desk = desk

    async def handle(self, query: FindTicketByNumber) -> Ticket:
        found = await self._desk.tickets.find_by_number(query.tenant_id, query.number)
        if found is None:
            raise TicketNotFoundError()
        ticket, _rights = await self._desk.load(query.tenant_id, query.actor, found.id)
        return ticket


@dataclass(frozen=True, kw_only=True)
class ListMessages(Query[Sequence[Message]]):
    tenant_id: str
    actor: Actor
    ticket_id: str


class ListMessagesHandler:
    def __init__(self, desk: Desk, messages: MessageRepository) -> None:
        self._desk = desk
        self._messages = messages

    async def handle(self, query: ListMessages) -> Sequence[Message]:
        ticket, _rights = await self._desk.load(query.tenant_id, query.actor, query.ticket_id)
        return await self._messages.of_ticket(ticket.tenant_id, ticket.id)


@dataclass(frozen=True, kw_only=True)
class TicketHistory(Query[Sequence[HistoryEntry]]):
    tenant_id: str
    actor: Actor
    ticket_id: str


class TicketHistoryHandler:
    def __init__(self, desk: Desk) -> None:
        self._desk = desk

    async def handle(self, query: TicketHistory) -> Sequence[HistoryEntry]:
        ticket, _rights = await self._desk.load(query.tenant_id, query.actor, query.ticket_id)
        return await self._desk.history.of_ticket(ticket.tenant_id, ticket.id)


@dataclass(frozen=True, kw_only=True)
class TicketTime(Query[Sequence[TimeEntry]]):
    tenant_id: str
    actor: Actor
    ticket_id: str


class TicketTimeHandler:
    def __init__(self, desk: Desk, times: TimeRepository) -> None:
        self._desk = desk
        self._times = times

    async def handle(self, query: TicketTime) -> Sequence[TimeEntry]:
        ticket, _rights = await self._desk.load(query.tenant_id, query.actor, query.ticket_id)
        return await self._times.of_ticket(ticket.tenant_id, ticket.id)


@dataclass(frozen=True, kw_only=True)
class Assignees(Query[list[str]]):
    """Who may get tickets of a queue: the members who may reply in it. Needs `view` in the queue."""

    tenant_id: str
    actor: Actor
    queue_id: str


class AssigneesHandler:
    def __init__(self, desk: Desk) -> None:
        self._desk = desk

    async def handle(self, query: Assignees) -> list[str]:
        if 'view' not in await self._desk.rights.rights(query.tenant_id, query.actor, query.queue_id):
            raise TicketNotFoundError()
        return await self._desk.rights.assignees(query.tenant_id, query.queue_id)


@dataclass(frozen=True, kw_only=True)
class TicketUsageQuery(Query[int]):
    """For the `TicketUsage` contract: tickets in a queue or of a customer."""

    tenant_id: str
    queue_id: str | None = None
    contact_id: str | None = None


class TicketUsageHandler:
    def __init__(self, desk: Desk) -> None:
        self._desk = desk

    async def handle(self, query: TicketUsageQuery) -> int:
        if query.queue_id is not None:
            return await self._desk.tickets.in_queue(query.tenant_id, query.queue_id)
        return await self._desk.tickets.of_customer(query.tenant_id, query.contact_id or '')


@dataclass(frozen=True, kw_only=True)
class SimilarTickets(Query[TicketList]):
    """Tickets about the same thing (words in the subject), among those the actor may see."""

    tenant_id: str
    actor: Actor
    ticket_id: str
    limit: int = 5


class SimilarTicketsHandler:
    def __init__(self, desk: Desk) -> None:
        self._desk = desk

    async def handle(self, query: SimilarTickets) -> TicketList:
        ticket, _rights = await self._desk.load(query.tenant_id, query.actor, query.ticket_id)
        visible = await self._desk.rights.visible(query.tenant_id, query.actor)
        found = await self._desk.tickets.similar(ticket.tenant_id, ticket.id, list(visible), query.limit)
        return TicketList([TicketWithRights(each, visible[each.queue_id]) for each in found], len(found))
