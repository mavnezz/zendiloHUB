from dataclasses import dataclass

from zendilohub.core.bus.message import Command
from zendilohub.core.domain.queue_rights import QueueRight
from zendilohub.core.domain.transaction import TransactionManager
from zendilohub.core.events.integration_events import MessageAdded, TicketCreated

from ...domain.exceptions import (
    LinkToItselfError,
    MergeIntoItselfError,
    MessageNotFoundError,
    TicketMergedError,
    TicketNotFoundError,
)
from ...domain.models.actor import Actor
from ...domain.models.link import Link, LinkKind
from ...domain.models.message import Message
from ...domain.models.ticket import Ticket
from ...domain.models.time_entry import TimeEntry
from ...domain.ports.repositories import LinkRepository, MessageRepository, WatcherRepository
from ..services.desk import Desk, TimeKeeper, require


@dataclass(frozen=True, kw_only=True)
class Watch(Command[None]):
    """Watching (like OTOBO's watcher): the ticket shows up in the caller's `watching` view."""

    tenant_id: str
    actor: Actor
    ticket_id: str
    on: bool = True


class WatchHandler:
    def __init__(self, desk: Desk, watchers: WatcherRepository) -> None:
        self._desk = desk
        self._watchers = watchers

    async def handle(self, command: Watch) -> None:
        ticket, _rights = await self._desk.load(command.tenant_id, command.actor, command.ticket_id)
        if command.on:
            await self._watchers.watch(ticket.tenant_id, ticket.id, [command.actor.user_id])
        else:
            await self._watchers.unwatch(ticket.tenant_id, ticket.id, command.actor.user_id)


async def _other(desk: Desk, tenant_id: str, actor: Actor, number: int) -> tuple[Ticket, frozenset[QueueRight]]:
    found = await desk.tickets.find_by_number(tenant_id, number)
    if found is None:
        raise TicketNotFoundError()
    return await desk.load(tenant_id, actor, found.id)


@dataclass(frozen=True, kw_only=True)
class LinkTickets(Command[Ticket]):
    """Links a ticket to another (by number): related, or the other one as its parent or child. Needs `edit`."""

    tenant_id: str
    actor: Actor
    ticket_id: str
    other_number: int
    kind: LinkKind = 'related'


class LinkTicketsHandler:
    def __init__(self, desk: Desk, links: LinkRepository, transactions: TransactionManager) -> None:
        self._desk = desk
        self._links = links
        self._transactions = transactions

    async def handle(self, command: LinkTickets) -> Ticket:
        desk, actor = self._desk, command.actor
        ticket, rights = await desk.load(command.tenant_id, actor, command.ticket_id)
        require(rights, 'edit')
        other, _other_rights = await _other(desk, command.tenant_id, actor, command.other_number)
        if other.id == ticket.id:
            raise LinkToItselfError()
        async with self._transactions.transaction():
            await self._links.link(ticket.tenant_id, Link(ticket_id=ticket.id, other_id=other.id, kind=command.kind))
            await desk.history.add(
                [
                    desk.entry(ticket, actor, 'linked', field=command.kind, new=str(other.number)),
                    desk.entry(other, actor, 'linked', field=command.kind, new=str(ticket.number)),
                ]
            )
        return other


@dataclass(frozen=True, kw_only=True)
class UnlinkTickets(Command[None]):
    tenant_id: str
    actor: Actor
    ticket_id: str
    other_id: str


class UnlinkTicketsHandler:
    def __init__(self, desk: Desk, links: LinkRepository) -> None:
        self._desk = desk
        self._links = links

    async def handle(self, command: UnlinkTickets) -> None:
        desk = self._desk
        ticket, rights = await desk.load(command.tenant_id, command.actor, command.ticket_id)
        require(rights, 'edit')
        if await self._links.kind_between(ticket.tenant_id, ticket.id, command.other_id) is None:
            raise TicketNotFoundError()
        other = await desk.tickets.find(ticket.tenant_id, command.other_id)
        await self._links.unlink(ticket.tenant_id, ticket.id, command.other_id)
        await desk.history.add(
            [desk.entry(ticket, command.actor, 'unlinked', new=str(other.number) if other else None)]
        )


@dataclass(frozen=True, kw_only=True)
class MergeTicket(Command[Ticket]):
    """
    Merges a ticket into another (by number), e.g. when a customer wrote twice: its messages, time, watchers and tags
    move over, it stays behind as `merged` pointing to the other. Needs `edit` in both queues.
    """

    tenant_id: str
    actor: Actor
    ticket_id: str
    into_number: int


class MergeTicketHandler:
    def __init__(
        self,
        desk: Desk,
        messages: MessageRepository,
        watchers: WatcherRepository,
        links: LinkRepository,
        transactions: TransactionManager,
    ) -> None:
        self._desk = desk
        self._messages = messages
        self._watchers = watchers
        self._links = links
        self._transactions = transactions

    async def handle(self, command: MergeTicket) -> Ticket:
        desk, actor = self._desk, command.actor
        async with self._transactions.transaction():
            source, rights = await desk.load(command.tenant_id, actor, command.ticket_id)
            target, target_rights = await _other(desk, command.tenant_id, actor, command.into_number)
            if source.id == target.id:
                raise MergeIntoItselfError()
            if source.is_merged or target.is_merged:
                raise TicketMergedError()
            require(rights, 'edit')
            require(target_rights, 'edit')
            now = desk.clock.now()
            await self._messages.move(source.tenant_id, source.id, target.id)
            await self._watchers.watch(
                target.tenant_id, target.id, list(await self._watchers.of_ticket(source.tenant_id, source.id))
            )
            target.retag((*target.tags, *source.tags), now)
            if target.state in ('closed', 'pending_close', 'pending_reminder'):
                target.set_state('open', now)
            source.merge_into(target, now)
            await self._links.link(source.tenant_id, Link(ticket_id=source.id, other_id=target.id, kind='related'))
            await desk.save(source, actor, [desk.entry(source, actor, 'merged', new=str(target.number))])
            await desk.save(target, actor, [desk.entry(target, actor, 'merged_from', new=str(source.number))])
        return target


@dataclass(frozen=True, kw_only=True)
class SplitTicket(Command[Ticket]):
    """A new ticket from one message of another (a second concern in the same mail); needs `create` and `view`."""

    tenant_id: str
    actor: Actor
    ticket_id: str
    message_id: str
    subject: str | None = None


class SplitTicketHandler:
    def __init__(
        self, desk: Desk, messages: MessageRepository, links: LinkRepository, transactions: TransactionManager
    ) -> None:
        self._desk = desk
        self._messages = messages
        self._links = links
        self._transactions = transactions

    async def handle(self, command: SplitTicket) -> Ticket:
        desk, actor = self._desk, command.actor
        source, rights = await desk.load(command.tenant_id, actor, command.ticket_id)
        require(rights, 'create')
        message = await self._messages.find(command.tenant_id, command.message_id)
        if message is None or message.ticket_id != source.id:
            raise MessageNotFoundError()
        now = desk.clock.now()
        async with self._transactions.transaction():
            ticket = Ticket.open(
                id=desk.ids.new_id(),
                tenant_id=source.tenant_id,
                number=await desk.next_number(source.tenant_id),
                subject=command.subject or source.subject,
                queue_id=source.queue_id,
                channel=source.channel,
                customer_id=source.customer_id,
                priority=source.priority,
                tags=source.tags,
                now=now,
            )
            ticket.last_message_at = message.created_at
            copy = Message(**{**vars(message), 'id': desk.ids.new_id(), 'ticket_id': ticket.id})
            ticket.changes.clear()
            await desk.tickets.save(ticket)
            await self._messages.save(copy)
            await self._links.link(source.tenant_id, Link(ticket_id=ticket.id, other_id=source.id, kind='related'))
            await desk.history.add(
                [
                    desk.entry(ticket, actor, 'created', new=str(ticket.number)),
                    desk.entry(ticket, actor, 'split_from', new=str(source.number)),
                ]
            )
            await desk.events.publish(
                TicketCreated(
                    tenant_id=ticket.tenant_id,
                    ticket_id=ticket.id,
                    number=ticket.number,
                    queue_id=ticket.queue_id,
                    customer_id=ticket.customer_id,
                    channel=ticket.channel,
                    actor_id=actor.user_id or None,
                )
            )
            await desk.events.publish(
                MessageAdded(
                    tenant_id=ticket.tenant_id,
                    ticket_id=ticket.id,
                    message_id=copy.id,
                    kind=copy.kind,
                    direction=copy.direction,
                    author_id=copy.author_id,
                    first=True,
                )
            )
        return ticket


@dataclass(frozen=True, kw_only=True)
class RecordTime(Command[TimeEntry]):
    """Time spent without a message (a call, research); needs `note`."""

    tenant_id: str
    actor: Actor
    ticket_id: str
    minutes: int


class RecordTimeHandler:
    def __init__(self, desk: Desk, time: TimeKeeper) -> None:
        self._desk = desk
        self._time = time

    async def handle(self, command: RecordTime) -> TimeEntry:
        ticket, rights = await self._desk.load(command.tenant_id, command.actor, command.ticket_id)
        require(rights, 'note')
        return await self._time.record(ticket, command.actor, command.minutes, None)
