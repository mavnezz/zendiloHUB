from collections.abc import Sequence

from zendilohub.core.domain.clock import Clock
from zendilohub.core.domain.id_generator import IdGenerator
from zendilohub.core.domain.queue_rights import QueueRight
from zendilohub.core.events.event_bus import EventBus
from zendilohub.core.events.integration_events import TicketChanged

from ...domain.exceptions import NotAssignableError, QueueRightMissingError, TicketNotFoundError
from ...domain.models.actor import Actor
from ...domain.models.history import HistoryAction, HistoryEntry
from ...domain.models.ticket import Ticket
from ...domain.models.time_entry import TimeEntry
from ...domain.ports.repositories import HistoryRepository, TicketRepository, TimeRepository
from ...domain.ports.services import QueueRights


def require(rights: frozenset[QueueRight], right: QueueRight) -> None:
    if right not in rights:
        raise QueueRightMissingError(right)


class Desk:
    """What every ticket command needs: tickets the actor may see, their rights, and the history."""

    def __init__(
        self,
        tickets: TicketRepository,
        history: HistoryRepository,
        rights: QueueRights,
        events: EventBus,
        ids: IdGenerator,
        clock: Clock,
    ) -> None:
        self.tickets = tickets
        self.history = history
        self.rights = rights
        self.events = events
        self.ids = ids
        self.clock = clock

    async def load(self, tenant_id: str, actor: Actor, ticket_id: str) -> tuple[Ticket, frozenset[QueueRight]]:
        """The ticket with the actor's rights in its queue; unknown to those who may not see it."""
        ticket = await self.tickets.find(tenant_id, ticket_id)
        if ticket is None:
            raise TicketNotFoundError()
        rights = await self.rights.rights(tenant_id, actor, ticket.queue_id)
        if 'view' not in rights:
            raise TicketNotFoundError()
        return ticket, rights

    def entry(
        self,
        ticket: Ticket,
        actor: Actor,
        action: HistoryAction,
        *,
        field: str | None = None,
        old: str | None = None,
        new: str | None = None,
    ) -> HistoryEntry:
        return HistoryEntry(
            id=self.ids.new_id(),
            tenant_id=ticket.tenant_id,
            ticket_id=ticket.id,
            actor_id=actor.user_id or None,
            actor_name=actor.name,
            action=action,
            field=field,
            old=old,
            new=new,
            created_at=self.clock.now(),
        )

    async def save(self, ticket: Ticket, actor: Actor, extra: Sequence[HistoryEntry] = ()) -> None:
        """Stores the ticket, writes its changes into the history and tells the other modules."""
        changes = list(ticket.changes)
        ticket.changes.clear()
        await self.tickets.save(ticket)
        entries = [
            self.entry(ticket, actor, 'changed', field=change.field, old=change.old, new=change.new)
            for change in changes
        ]
        await self.history.add([*entries, *extra])
        if changes:
            await self.events.publish(
                TicketChanged(
                    tenant_id=ticket.tenant_id,
                    ticket_id=ticket.id,
                    actor_id=actor.user_id or None,
                    changes=tuple((change.field, change.old, change.new) for change in changes),
                )
            )

    async def check_owner(
        self, ticket: Ticket, actor: Actor, owner_id: str | None, rights: frozenset[QueueRight], queue_id: str
    ) -> None:
        """Taking a ticket needs `reply`; giving it to someone else (or taking it away) needs `assign`."""
        own = owner_id is not None and owner_id == actor.user_id
        leave_own = owner_id is None and ticket.owner_id == actor.user_id
        require(rights, 'reply' if own or leave_own else 'assign')
        if owner_id is not None and owner_id not in await self.rights.assignees(ticket.tenant_id, queue_id):
            raise NotAssignableError()


class TimeKeeper:
    """Records time spent on a ticket (when creating it, with a message, or on its own)."""

    def __init__(self, desk: Desk, times: TimeRepository) -> None:
        self._desk = desk
        self._times = times

    async def record(self, ticket: Ticket, actor: Actor, minutes: int, message_id: str | None) -> TimeEntry:
        entry = TimeEntry.record(
            id=self._desk.ids.new_id(),
            tenant_id=ticket.tenant_id,
            ticket_id=ticket.id,
            user_id=actor.user_id,
            minutes=minutes,
            message_id=message_id,
            now=self._desk.clock.now(),
        )
        await self._times.add(entry)
        await self._desk.history.add([self._desk.entry(ticket, actor, 'time', new=str(minutes))])
        return entry
