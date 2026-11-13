from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from zendilohub.core.bus.message import Command
from zendilohub.core.domain.transaction import TransactionManager
from zendilohub.core.events.integration_events import MessageAdded

from ...domain.exceptions import InvalidMessageError, TicketMergedError
from ...domain.models.actor import Actor
from ...domain.models.message import Direction, Message, MessageKind
from ...domain.models.ticket import TicketState
from ...domain.ports.repositories import MessageRepository, WatcherRepository
from ..services.desk import Desk, TimeKeeper, require


@dataclass(frozen=True, kw_only=True)
class AddMessage(Command[Message]):
    """
    A reply to the customer (`public`, `out`; needs `reply`), an internal note (`internal`; needs `note`) or what the
    customer said, written down by the team (`public`, `in`; needs `reply`). The state can change along with it
    (`edit`); mentioned members start watching the ticket.
    """

    tenant_id: str
    actor: Actor
    ticket_id: str
    kind: MessageKind
    body: str
    direction: Direction = 'out'
    state: TicketState | None = None
    pending_until: datetime | None = None
    time_minutes: int | None = None
    mentions: Sequence[str] = ()


class AddMessageHandler:
    def __init__(
        self,
        desk: Desk,
        messages: MessageRepository,
        watchers: WatcherRepository,
        time: TimeKeeper,
        transactions: TransactionManager,
    ) -> None:
        self._desk = desk
        self._messages = messages
        self._watchers = watchers
        self._time = time
        self._transactions = transactions

    async def handle(self, command: AddMessage) -> Message:
        desk, actor = self._desk, command.actor
        async with self._transactions.transaction():
            ticket, rights = await desk.load(command.tenant_id, actor, command.ticket_id)
            if ticket.is_merged:
                raise TicketMergedError()
            require(rights, 'note' if command.kind == 'internal' else 'reply')
            if command.state is not None:
                require(rights, 'edit')
            for user_id in command.mentions:
                if not await desk.rights.is_member(command.tenant_id, user_id):
                    raise InvalidMessageError('mentions')
            now = desk.clock.now()
            inbound = command.direction == 'in'
            message = Message.write(
                id=desk.ids.new_id(),
                tenant_id=ticket.tenant_id,
                ticket_id=ticket.id,
                kind=command.kind,
                direction=command.direction,
                author_kind='customer' if inbound else 'agent',
                author_id=ticket.customer_id if inbound else actor.user_id or None,
                author_name='' if inbound else actor.name,
                body=command.body,
                now=now,
            )
            if command.kind == 'internal':
                ticket.noted(now)
            elif inbound:
                ticket.received(now)
            else:
                ticket.answered(now)
            if command.state is not None:
                ticket.set_state(command.state, now, pending_until=command.pending_until)
            await self._messages.save(message)
            await desk.save(ticket, actor, [desk.entry(ticket, actor, 'message', new=message.kind)])
            if command.time_minutes:
                await self._time.record(ticket, actor, command.time_minutes, message.id)
            if command.mentions:
                await self._watchers.watch(ticket.tenant_id, ticket.id, list(dict.fromkeys(command.mentions)))
            await desk.events.publish(
                MessageAdded(
                    tenant_id=ticket.tenant_id,
                    ticket_id=ticket.id,
                    message_id=message.id,
                    kind=message.kind,
                    direction=message.direction,
                    author_id=message.author_id,
                    mentions=tuple(dict.fromkeys(command.mentions)),
                    automated=actor.automated,
                )
            )
        return message
