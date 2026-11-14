from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from zendilohub.core.bus.message import Command
from zendilohub.core.domain.app_domain_error import AppDomainError
from zendilohub.core.domain.queue_rights import QueueRight
from zendilohub.core.domain.transaction import TransactionManager
from zendilohub.core.events.integration_events import MessageAdded, TicketCreated

from ...domain.exceptions import InvalidFieldError, InvalidTicketError, TicketMergedError
from ...domain.models.actor import Actor
from ...domain.models.message import Message
from ...domain.models.ticket import Channel, Priority, Ticket, TicketState
from ...domain.models.unset import UNSET, Unset
from ...domain.ports.repositories import FieldRepository, MessageRepository
from ...domain.ports.services import CustomerDirectory
from ..services.desk import Desk, TimeKeeper, require

type FirstMessage = Literal['customer', 'reply', 'note']
"""
What the new ticket starts with: what the `customer` said (on the phone, at the counter), a `reply` the team sends to
the customer, or an internal `note`.
"""


@dataclass(frozen=True, kw_only=True)
class CustomerRef:
    """An existing contact by id, or one found (or made) by e-mail address or phone number."""

    id: str | None = None
    email: str | None = None
    name: str = ''
    phone: str | None = None


@dataclass(frozen=True, kw_only=True)
class CreateTicket(Command[Ticket]):
    tenant_id: str
    actor: Actor
    queue_id: str
    subject: str
    body: str
    first: FirstMessage = 'customer'
    customer: CustomerRef | None = None
    channel: Channel = 'web'
    priority: Priority = 'normal'
    tags: tuple[str, ...] = ()
    owner_id: str | None = None
    state: TicketState | None = None
    pending_until: datetime | None = None
    time_minutes: int | None = None


class CreateTicketHandler:
    def __init__(
        self,
        desk: Desk,
        messages: MessageRepository,
        customers: CustomerDirectory,
        transactions: TransactionManager,
        time: TimeKeeper,
    ) -> None:
        self._desk = desk
        self._messages = messages
        self._customers = customers
        self._transactions = transactions
        self._time = time

    async def handle(self, command: CreateTicket) -> Ticket:
        desk, actor = self._desk, command.actor
        rights = await desk.rights.rights(command.tenant_id, actor, command.queue_id)
        require(rights, 'create')
        if command.first == 'reply':
            require(rights, 'reply')
        if command.first == 'note':
            require(rights, 'note')
        customer_id = await self._customer(command)
        now = desk.clock.now()
        async with self._transactions.transaction():
            ticket = Ticket.open(
                id=desk.ids.new_id(),
                tenant_id=command.tenant_id,
                number=await desk.next_number(command.tenant_id),
                subject=command.subject,
                queue_id=command.queue_id,
                channel=command.channel,
                customer_id=customer_id,
                priority=command.priority,
                tags=command.tags,
                now=now,
            )
            message = Message.write(
                id=desk.ids.new_id(),
                tenant_id=ticket.tenant_id,
                ticket_id=ticket.id,
                kind='internal' if command.first == 'note' else 'public',
                direction='in' if command.first == 'customer' else 'out',
                author_kind='customer' if command.first == 'customer' else 'agent',
                author_id=customer_id if command.first == 'customer' else actor.user_id or None,
                author_name=actor.name if command.first != 'customer' else '',
                body=command.body,
                now=now,
            )
            if command.first == 'customer':
                ticket.received(now)
            elif command.first == 'reply':
                ticket.answered(now)
            if command.owner_id is not None:
                await desk.check_owner(ticket, actor, command.owner_id, rights, ticket.queue_id)
                ticket.assign(command.owner_id, now)
            if command.state is not None:
                require(rights, 'edit')
                ticket.set_state(command.state, now, pending_until=command.pending_until)
            ticket.changes.clear()
            await desk.tickets.save(ticket)
            await self._messages.save(message)
            await desk.history.add([desk.entry(ticket, actor, 'created', new=str(ticket.number))])
            if command.time_minutes:
                await self._time.record(ticket, actor, command.time_minutes, message.id)
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
                    message_id=message.id,
                    kind=message.kind,
                    direction=message.direction,
                    author_id=message.author_id,
                    first=True,
                )
            )
        return ticket

    async def _customer(self, command: CreateTicket) -> str | None:
        ref = command.customer
        if ref is None:
            return None
        if ref.id is not None:
            if not await self._customers.exists(command.tenant_id, ref.id):
                raise InvalidTicketError('customer')
            return ref.id
        if not (ref.email or ref.phone):
            raise InvalidTicketError('customer')
        return await self._customers.identify(command.tenant_id, email=ref.email, name=ref.name, phone=ref.phone)


@dataclass(frozen=True, kw_only=True)
class TicketChanges:
    """What to change; UNSET fields stay as they are."""

    subject: str | Unset = UNSET
    state: TicketState | Unset = UNSET
    pending_until: datetime | Unset | None = UNSET
    priority: Priority | Unset = UNSET
    owner_id: str | Unset | None = UNSET
    responsible_id: str | Unset | None = UNSET
    queue_id: str | Unset = UNSET
    tags: tuple[str, ...] | Unset = UNSET
    add_tags: tuple[str, ...] = ()
    customer_id: str | Unset | None = UNSET
    fields: Mapping[str, object] | Unset = UNSET
    """Values of own fields by key; null (or empty) clears one."""


@dataclass(frozen=True, kw_only=True)
class UpdateTicket(Command[Ticket]):
    tenant_id: str
    actor: Actor
    ticket_id: str
    changes: TicketChanges


class UpdateTicketHandler:
    def __init__(
        self,
        desk: Desk,
        customers: CustomerDirectory,
        transactions: TransactionManager,
        fields: FieldRepository,
    ) -> None:
        self._desk = desk
        self._customers = customers
        self._transactions = transactions
        self._fields = fields

    async def handle(self, command: UpdateTicket) -> Ticket:
        async with self._transactions.transaction():
            ticket, rights = await self._desk.load(command.tenant_id, command.actor, command.ticket_id)
            await self.apply(ticket, rights, command.actor, command.changes)
            await self._desk.save(ticket, command.actor)
        return ticket

    async def apply(self, ticket: Ticket, rights: frozenset[QueueRight], actor: Actor, changes: TicketChanges) -> None:
        desk, now = self._desk, self._desk.clock.now()
        if ticket.is_merged:
            raise TicketMergedError()
        edits = [changes.subject, changes.state, changes.priority, changes.tags, changes.customer_id, changes.fields]
        if any(not isinstance(value, Unset) for value in edits) or changes.add_tags:
            require(rights, 'edit')
        if not isinstance(changes.responsible_id, Unset):
            require(rights, 'edit')
            if changes.responsible_id is not None and not await desk.rights.is_member(
                ticket.tenant_id, changes.responsible_id
            ):
                raise InvalidTicketError('responsible_id')
            ticket.make_responsible(changes.responsible_id, now)
        if not isinstance(changes.subject, Unset):
            ticket.rename(changes.subject, now)
        if not isinstance(changes.fields, Unset):
            definitions = {each.key: each for each in await self._fields.of_tenant(ticket.tenant_id)}
            for key, raw in changes.fields.items():
                if key not in definitions:
                    raise InvalidFieldError(key)
                ticket.set_field(key, definitions[key].value(raw), now)
        if not isinstance(changes.priority, Unset):
            ticket.set_priority(changes.priority, now)
        if not isinstance(changes.tags, Unset):
            ticket.retag(changes.tags, now)
        if changes.add_tags:
            ticket.retag((*ticket.tags, *changes.add_tags), now)
        if not isinstance(changes.customer_id, Unset):
            if changes.customer_id is not None and not await self._customers.exists(
                ticket.tenant_id, changes.customer_id
            ):
                raise InvalidTicketError('customer_id')
            ticket.change_customer(changes.customer_id, now)
        if not isinstance(changes.state, Unset):
            pending = None if isinstance(changes.pending_until, Unset) else changes.pending_until
            ticket.set_state(changes.state, now, pending_until=pending)
        elif not isinstance(changes.pending_until, Unset):
            require(rights, 'edit')
            ticket.set_state(ticket.state, now, pending_until=changes.pending_until)
        if not isinstance(changes.owner_id, Unset) and changes.owner_id != ticket.owner_id:
            # Assigned in the queue the ticket lies in now, before it moves.
            await desk.check_owner(ticket, actor, changes.owner_id, rights, ticket.queue_id)
            ticket.assign(changes.owner_id, now)
        if not isinstance(changes.queue_id, Unset) and changes.queue_id != ticket.queue_id:
            require(rights, 'move')
            require(await desk.rights.rights(ticket.tenant_id, actor, changes.queue_id), 'create')
            ticket.move(changes.queue_id, now)
            if ticket.owner_id and ticket.owner_id not in await desk.rights.assignees(
                ticket.tenant_id, ticket.queue_id
            ):
                # Who may not reply in the new queue cannot keep the ticket.
                ticket.assign(None, now)


@dataclass(frozen=True, kw_only=True)
class BulkResult:
    changed: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    """Ticket id → error code."""


@dataclass(frozen=True, kw_only=True)
class BulkUpdate(Command[BulkResult]):
    """The same changes for many tickets (like OTOBO's bulk action); tickets the caller may not change are reported."""

    tenant_id: str
    actor: Actor
    ticket_ids: Sequence[str]
    changes: TicketChanges


class BulkUpdateHandler:
    def __init__(self, update: UpdateTicketHandler) -> None:
        self._update = update

    async def handle(self, command: BulkUpdate) -> BulkResult:
        result = BulkResult()
        for ticket_id in dict.fromkeys(command.ticket_ids):
            try:
                await self._update.handle(
                    UpdateTicket(
                        tenant_id=command.tenant_id, actor=command.actor, ticket_id=ticket_id, changes=command.changes
                    )
                )
                result.changed.append(ticket_id)
            except AppDomainError as error:
                result.failed[ticket_id] = error.code
        return result


@dataclass(frozen=True, kw_only=True)
class DeleteTicket(Command[Ticket]):
    """Needs `tickets.delete` (checked by the route) and the queue's `view`."""

    tenant_id: str
    actor: Actor
    ticket_id: str


class DeleteTicketHandler:
    def __init__(self, desk: Desk) -> None:
        self._desk = desk

    async def handle(self, command: DeleteTicket) -> Ticket:
        ticket, _rights = await self._desk.load(command.tenant_id, command.actor, command.ticket_id)
        await self._desk.tickets.delete(command.tenant_id, ticket.id)
        return ticket
