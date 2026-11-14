from dataclasses import dataclass

from zendilohub.core.bus.message import Command, Query
from zendilohub.core.domain.portal import PortalMessage, PortalThread, PortalTicket
from zendilohub.core.domain.transaction import TransactionManager
from zendilohub.core.events.integration_events import MessageAdded, TicketCreated

from ...domain.models.actor import Actor
from ...domain.models.message import Message
from ...domain.models.ticket import Ticket
from ...domain.ports.repositories import MessageRepository
from ..services.desk import Desk


def _portal(ticket: Ticket) -> PortalTicket:
    return PortalTicket(
        id=ticket.id,
        number=ticket.number,
        subject=ticket.subject,
        state='closed' if ticket.state == 'closed' else 'waiting' if ticket.state.startswith('pending') else 'open',
        customer_id=ticket.customer_id,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
    )


@dataclass(frozen=True, kw_only=True)
class PortalTickets(Query[list[PortalTicket]]):
    tenant_id: str
    contact_ids: tuple[str, ...]


class PortalTicketsHandler:
    def __init__(self, desk: Desk) -> None:
        self._desk = desk

    async def handle(self, query: PortalTickets) -> list[PortalTicket]:
        found = await self._desk.tickets.of_customers(query.tenant_id, query.contact_ids, 200)
        return [_portal(each) for each in found]


@dataclass(frozen=True, kw_only=True)
class PortalThreadQuery(Query[PortalThread | None]):
    tenant_id: str
    contact_ids: tuple[str, ...]
    ticket_id: str


class PortalThreadHandler:
    def __init__(self, desk: Desk, messages: MessageRepository) -> None:
        self._desk = desk
        self._messages = messages

    async def handle(self, query: PortalThreadQuery) -> PortalThread | None:
        ticket = await self._desk.tickets.find(query.tenant_id, query.ticket_id)
        if ticket is None or ticket.customer_id not in query.contact_ids or ticket.is_merged:
            return None
        public = [each for each in await self._messages.of_ticket(ticket.tenant_id, ticket.id) if each.kind == 'public']
        return PortalThread(
            ticket=_portal(ticket),
            messages=[
                PortalMessage(
                    id=each.id,
                    from_customer=each.direction == 'in',
                    # Agents appear by first name part only; customers see no team addresses.
                    author_name=each.author_name if each.direction == 'in' else each.author_name.split('@')[0],
                    body=each.body,
                    created_at=each.created_at,
                )
                for each in public
            ],
        )


@dataclass(frozen=True, kw_only=True)
class PortalReply(Command[bool]):
    tenant_id: str
    contact_id: str
    contact_ids: tuple[str, ...]
    ticket_id: str
    body: str


class PortalReplyHandler:
    def __init__(self, desk: Desk, messages: MessageRepository, transactions: TransactionManager) -> None:
        self._desk = desk
        self._messages = messages
        self._transactions = transactions

    async def handle(self, command: PortalReply) -> bool:
        desk = self._desk
        async with self._transactions.transaction():
            ticket = await desk.tickets.find(command.tenant_id, command.ticket_id)
            if ticket is None or ticket.customer_id not in command.contact_ids or ticket.is_merged:
                return False
            now = desk.clock.now()
            message = Message.write(
                id=desk.ids.new_id(),
                tenant_id=ticket.tenant_id,
                ticket_id=ticket.id,
                kind='public',
                direction='in',
                author_kind='customer',
                author_id=command.contact_id,
                author_name='',
                body=command.body,
                now=now,
            )
            actor = Actor(user_id='', name='Portal', person=False)
            ticket.received(now)
            await self._messages.save(message)
            await desk.save(ticket, actor, [desk.entry(ticket, actor, 'message', new='public')])
            await desk.events.publish(
                MessageAdded(
                    tenant_id=ticket.tenant_id,
                    ticket_id=ticket.id,
                    message_id=message.id,
                    kind='public',
                    direction='in',
                    author_id=command.contact_id,
                )
            )
        return True


@dataclass(frozen=True, kw_only=True)
class PortalOpen(Command[PortalTicket]):
    tenant_id: str
    contact_id: str
    queue_id: str
    subject: str
    body: str


class PortalOpenHandler:
    def __init__(self, desk: Desk, messages: MessageRepository, transactions: TransactionManager) -> None:
        self._desk = desk
        self._messages = messages
        self._transactions = transactions

    async def handle(self, command: PortalOpen) -> PortalTicket:
        desk, now = self._desk, self._desk.clock.now()
        actor = Actor(user_id='', name='Portal', person=False)
        async with self._transactions.transaction():
            ticket = Ticket.open(
                id=desk.ids.new_id(),
                tenant_id=command.tenant_id,
                number=await desk.tickets.next_number(command.tenant_id),
                subject=command.subject,
                queue_id=command.queue_id,
                channel='web',
                customer_id=command.contact_id,
                priority='normal',
                tags=(),
                now=now,
            )
            message = Message.write(
                id=desk.ids.new_id(),
                tenant_id=ticket.tenant_id,
                ticket_id=ticket.id,
                kind='public',
                direction='in',
                author_kind='customer',
                author_id=command.contact_id,
                author_name='',
                body=command.body,
                now=now,
            )
            ticket.received(now)
            ticket.changes.clear()
            await desk.tickets.save(ticket)
            await self._messages.save(message)
            await desk.history.add([desk.entry(ticket, actor, 'created', new=str(ticket.number))])
            await desk.events.publish(
                TicketCreated(
                    tenant_id=ticket.tenant_id,
                    ticket_id=ticket.id,
                    number=ticket.number,
                    queue_id=ticket.queue_id,
                    customer_id=ticket.customer_id,
                    channel='web',
                    actor_id=None,
                )
            )
            await desk.events.publish(
                MessageAdded(
                    tenant_id=ticket.tenant_id,
                    ticket_id=ticket.id,
                    message_id=message.id,
                    kind='public',
                    direction='in',
                    author_id=command.contact_id,
                    first=True,
                )
            )
        return _portal(ticket)
