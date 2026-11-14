from dataclasses import dataclass

from zendilohub.core.bus.message import Command, Query
from zendilohub.core.domain.inbox import InboundEmail, OutgoingEmail, ReceivedTicket
from zendilohub.core.domain.transaction import TransactionManager
from zendilohub.core.events.integration_events import MessageAdded, TicketCreated

from ...domain.models.actor import Actor
from ...domain.models.message import Message
from ...domain.models.ticket import PRIORITIES, SUBJECT_MAX, Priority, Ticket
from ...domain.ports.repositories import MessageRepository
from ...domain.ports.services import CustomerDirectory
from ..services.desk import Desk
from ..services.files import Files

NO_SUBJECT = '(no subject)'


@dataclass(frozen=True)
class ReceiveEmail(Command[ReceivedTicket]):
    """An e-mail came in: it joins its ticket, or opens a new one (the customer is found or made by address)."""

    email: InboundEmail


class ReceiveEmailHandler:
    def __init__(
        self,
        desk: Desk,
        messages: MessageRepository,
        customers: CustomerDirectory,
        transactions: TransactionManager,
        files: Files,
    ) -> None:
        self._desk = desk
        self._messages = messages
        self._customers = customers
        self._transactions = transactions
        self._files = files

    async def handle(self, command: ReceiveEmail) -> ReceivedTicket:
        email, desk = command.email, self._desk
        customer_id = await self._customers.identify(
            email.tenant_id, email=email.from_address, name=email.from_name, phone=None
        )
        actor = Actor(user_id='', name=email.from_address, person=False)
        now = desk.clock.now()
        async with self._transactions.transaction():
            ticket = await self._existing(email)
            created = ticket is None
            if ticket is None:
                ticket = Ticket.open(
                    id=desk.ids.new_id(),
                    tenant_id=email.tenant_id,
                    number=await desk.next_number(email.tenant_id),
                    subject=(' '.join(email.subject.split()) or NO_SUBJECT)[:SUBJECT_MAX],
                    queue_id=email.queue_id,
                    channel='email',
                    customer_id=customer_id,
                    priority=_priority(email.priority),
                    tags=email.tags,
                    now=now,
                )
            message = Message.write(
                id=desk.ids.new_id(),
                tenant_id=ticket.tenant_id,
                ticket_id=ticket.id,
                kind='public',
                direction='in',
                author_kind='customer',
                author_id=customer_id,
                author_name=email.from_name,
                body=email.body or ('' if email.body_html or email.attachments else NO_SUBJECT),
                now=now,
                with_files=bool(email.attachments),
                body_html=email.body_html,
                subject=email.subject or None,
                from_address=email.from_address,
                to_addresses=email.to_addresses,
                cc_addresses=email.cc_addresses,
                email_message_id=email.email_message_id,
                in_reply_to=email.in_reply_to,
                references=email.references,
                security=email.security,
            )
            ticket.received(now)
            if created:
                ticket.changes.clear()
                await desk.tickets.save(ticket)
                await desk.history.add([desk.entry(ticket, actor, 'created', new=str(ticket.number))])
            await self._messages.save(message)
            await self._files.add_all(message, email.attachments)
            await desk.save(ticket, actor, [desk.entry(ticket, actor, 'message', new='public')])
            if created:
                await desk.events.publish(
                    TicketCreated(
                        tenant_id=ticket.tenant_id,
                        ticket_id=ticket.id,
                        number=ticket.number,
                        queue_id=ticket.queue_id,
                        customer_id=ticket.customer_id,
                        channel='email',
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
                    author_id=customer_id,
                    first=created,
                )
            )
        return ReceivedTicket(ticket_id=ticket.id, number=ticket.number, created=created, customer_id=customer_id)

    async def _existing(self, email: InboundEmail) -> Ticket | None:
        if email.ticket_id is None:
            return None
        ticket = await self._desk.tickets.find(email.tenant_id, email.ticket_id)
        # A merged ticket lives on in the one it went into.
        for _ in range(5):
            if ticket is None or ticket.merged_into_id is None:
                break
            ticket = await self._desk.tickets.find(email.tenant_id, ticket.merged_into_id)
        return ticket


def _priority(value: str | None) -> Priority:
    for priority in PRIORITIES:
        if priority == value:
            return priority
    return 'normal'


@dataclass(frozen=True, kw_only=True)
class ThreadEmail(Query[str | None]):
    tenant_id: str
    email_ids: tuple[str, ...]
    number: int | None


class ThreadEmailHandler:
    def __init__(self, desk: Desk, messages: MessageRepository) -> None:
        self._desk = desk
        self._messages = messages

    async def handle(self, query: ThreadEmail) -> str | None:
        found = await self._messages.ticket_of_email(query.tenant_id, query.email_ids)
        if found is not None or query.number is None:
            return found
        ticket = await self._desk.tickets.find_by_number(query.tenant_id, query.number)
        return ticket.id if ticket else None


@dataclass(frozen=True, kw_only=True)
class OutgoingOf(Query[OutgoingEmail | None]):
    tenant_id: str
    message_id: str


class OutgoingOfHandler:
    def __init__(self, desk: Desk, messages: MessageRepository, customers: CustomerDirectory, files: Files) -> None:
        self._desk = desk
        self._messages = messages
        self._customers = customers
        self._files = files

    async def handle(self, query: OutgoingOf) -> OutgoingEmail | None:
        message = await self._messages.find(query.tenant_id, query.message_id)
        if message is None or message.kind != 'public' or message.direction != 'out':
            return None
        ticket = await self._desk.tickets.find(query.tenant_id, message.ticket_id)
        if ticket is None:
            return None
        email, name = await self._customers.address_of(ticket.tenant_id, ticket.customer_id)
        earlier = [
            each.email_message_id
            for each in await self._messages.of_ticket(ticket.tenant_id, ticket.id)
            if each.email_message_id and each.id != message.id
        ]
        return OutgoingEmail(
            ticket_id=ticket.id,
            number=ticket.number,
            subject=ticket.subject,
            queue_id=ticket.queue_id,
            customer_email=email,
            customer_name=name,
            body=message.body,
            author_id=message.author_id,
            references=tuple(earlier),
            attachments=tuple([data for each in message.attachments if (data := await self._files.content(each))]),
        )


@dataclass(frozen=True, kw_only=True)
class MarkSent(Command[None]):
    tenant_id: str
    message_id: str
    email_message_id: str
    from_address: str
    to: tuple[str, ...]


class MarkSentHandler:
    def __init__(self, messages: MessageRepository) -> None:
        self._messages = messages

    async def handle(self, command: MarkSent) -> None:
        await self._messages.set_email(
            command.tenant_id,
            command.message_id,
            email_message_id=command.email_message_id,
            from_address=command.from_address,
            to=command.to,
        )
