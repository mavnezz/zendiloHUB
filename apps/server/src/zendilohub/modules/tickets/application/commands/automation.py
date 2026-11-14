from dataclasses import dataclass
from datetime import timedelta

from zendilohub.core.bus.message import Command, Query
from zendilohub.core.domain.automation import AutomationChanges, TicketCriteria, TicketFacts
from zendilohub.core.domain.transaction import TransactionManager
from zendilohub.core.events.integration_events import MessageAdded

from ...domain.models.actor import Actor
from ...domain.models.message import Message
from ...domain.models.ticket import PENDING_STATES, PRIORITIES, SETTABLE_STATES
from ...domain.ports.repositories import MessageRepository, WatcherRepository
from ...domain.ports.services import CustomerDirectory
from ..services.desk import Desk


@dataclass(frozen=True, kw_only=True)
class FactsOf(Query[TicketFacts | None]):
    tenant_id: str
    ticket_id: str


class FactsOfHandler:
    def __init__(self, desk: Desk, watchers: WatcherRepository, customers: CustomerDirectory) -> None:
        self._desk = desk
        self._watchers = watchers
        self._customers = customers

    async def handle(self, query: FactsOf) -> TicketFacts | None:
        ticket = await self._desk.tickets.find(query.tenant_id, query.ticket_id)
        if ticket is None:
            return None
        email, _name = await self._customers.address_of(ticket.tenant_id, ticket.customer_id)
        return TicketFacts(
            id=ticket.id,
            number=ticket.number,
            subject=ticket.subject,
            queue_id=ticket.queue_id,
            state=ticket.state,
            priority=ticket.priority,
            channel=ticket.channel,
            tags=ticket.tags,
            owner_id=ticket.owner_id,
            responsible_id=ticket.responsible_id,
            customer_id=ticket.customer_id,
            customer_email=email,
            watchers=tuple(await self._watchers.of_ticket(ticket.tenant_id, ticket.id)),
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
            pending_until=ticket.pending_until,
            last_message_at=ticket.last_message_at,
            fields=dict(ticket.fields),
        )


@dataclass(frozen=True, kw_only=True)
class ExcerptOf(Query[str]):
    """The beginning of the newest public message of a ticket."""

    tenant_id: str
    ticket_id: str
    limit: int = 500


class ExcerptOfHandler:
    def __init__(self, messages: MessageRepository) -> None:
        self._messages = messages

    async def handle(self, query: ExcerptOf) -> str:
        public = [
            each for each in await self._messages.of_ticket(query.tenant_id, query.ticket_id) if each.kind == 'public'
        ]
        if not public:
            return ''
        text = public[-1].body.strip()
        return text if len(text) <= query.limit else text[: query.limit - 1].rstrip() + '…'


@dataclass(frozen=True, kw_only=True)
class FindTickets(Query[list[str]]):
    tenant_id: str
    criteria: TicketCriteria


class FindTicketsHandler:
    def __init__(self, desk: Desk) -> None:
        self._desk = desk

    async def handle(self, query: FindTickets) -> list[str]:
        return await self._desk.tickets.matching(query.tenant_id, query.criteria, self._desk.clock.now())


@dataclass(frozen=True, kw_only=True)
class ApplyAutomation(Command[bool]):
    """A trigger or scheduled job changes a ticket, whatever anyone's rights (it was set up by an administrator)."""

    tenant_id: str
    ticket_id: str
    changes: AutomationChanges
    by: str


class ApplyAutomationHandler:
    def __init__(self, desk: Desk, messages: MessageRepository, transactions: TransactionManager) -> None:
        self._desk = desk
        self._messages = messages
        self._transactions = transactions

    async def handle(self, command: ApplyAutomation) -> bool:
        desk, changes = self._desk, command.changes
        actor = Actor(user_id='', name=command.by, person=False, automated=True)
        async with self._transactions.transaction():
            ticket = await desk.tickets.find(command.tenant_id, command.ticket_id)
            if ticket is None or ticket.is_merged:
                return False
            now = desk.clock.now()
            if changes.state in SETTABLE_STATES:
                pending = (
                    now + timedelta(hours=changes.pending_hours or 24) if changes.state in PENDING_STATES else None
                )
                ticket.set_state(changes.state, now, pending_until=pending)
            if changes.priority in PRIORITIES:
                ticket.set_priority(changes.priority, now)
            if changes.queue_id and await desk.rights.rights(
                ticket.tenant_id, Actor(user_id='', name='', all_queues=True), changes.queue_id
            ):
                ticket.move(changes.queue_id, now)
                if ticket.owner_id and ticket.owner_id not in await desk.rights.assignees(
                    ticket.tenant_id, ticket.queue_id
                ):
                    ticket.assign(None, now)
            if changes.unassign:
                ticket.assign(None, now)
            elif changes.owner_id and changes.owner_id in await desk.rights.assignees(
                ticket.tenant_id, ticket.queue_id
            ):
                ticket.assign(changes.owner_id, now)
            if changes.add_tags or changes.remove_tags:
                removed = set(changes.remove_tags)
                ticket.retag([tag for tag in (*ticket.tags, *changes.add_tags) if tag not in removed], now)
            messages: list[Message] = []
            for kind, text in (('internal', changes.note), ('public', changes.reply)):
                if text and text.strip():
                    messages.append(
                        Message.write(
                            id=desk.ids.new_id(),
                            tenant_id=ticket.tenant_id,
                            ticket_id=ticket.id,
                            kind=kind,  # type: ignore[arg-type]
                            direction='out',
                            author_kind='system',
                            author_id=None,
                            author_name=command.by,
                            body=text,
                            now=now,
                        )
                    )
            changed = bool(ticket.changes or messages)
            for message in messages:
                await self._messages.save(message)
                if message.kind == 'public':
                    ticket.answered(now)
            await desk.save(ticket, actor, [desk.entry(ticket, actor, 'message', new=each.kind) for each in messages])
            for message in messages:
                await desk.events.publish(
                    MessageAdded(
                        tenant_id=ticket.tenant_id,
                        ticket_id=ticket.id,
                        message_id=message.id,
                        kind=message.kind,
                        direction='out',
                        author_id=None,
                        automated=True,
                    )
                )
        return changed
