from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ..models.history import HistoryEntry
from ..models.link import Link, LinkKind
from ..models.message import Message
from ..models.ticket import Ticket
from ..models.time_entry import TimeEntry
from ..models.views import TicketFilter, TicketView


@dataclass(frozen=True)
class TicketPage:
    items: Sequence[Ticket]
    total: int


class TicketRepository(Protocol):
    async def next_number(self, tenant_id: str) -> int:
        """The organization's next ticket number (1001, 1002, …), never handed out twice."""
        ...

    async def find(self, tenant_id: str, ticket_id: str) -> Ticket | None: ...

    async def find_by_number(self, tenant_id: str, number: int) -> Ticket | None: ...

    async def find_many(self, tenant_id: str, ticket_ids: Sequence[str]) -> Sequence[Ticket]: ...

    async def save(self, ticket: Ticket) -> None: ...

    async def delete(self, tenant_id: str, ticket_id: str) -> None:
        """With its messages, history, links, watchers and time."""
        ...

    async def search(self, criteria: TicketFilter) -> TicketPage: ...

    async def counts(self, criteria: TicketFilter) -> dict[TicketView, int]:
        """How many tickets each view has (`all` and `closed` left out: they only grow)."""
        ...

    async def in_queue(self, tenant_id: str, queue_id: str) -> int: ...

    async def of_customer(self, tenant_id: str, contact_id: str) -> int: ...

    async def due_to_close(self, now: datetime, limit: int) -> Sequence[Ticket]:
        """`pending_close` tickets of every organization whose date has come."""
        ...

    async def unassign(self, tenant_id: str | None, user_id: str, now: datetime) -> None:
        """Someone left (or every organization, for None): their tickets go back to nobody."""
        ...

    async def forget_tenant(self, tenant_id: str) -> None: ...


class MessageRepository(Protocol):
    async def of_ticket(self, tenant_id: str, ticket_id: str) -> Sequence[Message]:
        """Oldest first."""
        ...

    async def find(self, tenant_id: str, message_id: str) -> Message | None: ...

    async def save(self, message: Message) -> None: ...

    async def move(self, tenant_id: str, from_ticket: str, to_ticket: str) -> None:
        """Merging: the messages (and time) of one ticket go to the other."""
        ...

    async def ticket_of_email(self, tenant_id: str, email_ids: Sequence[str]) -> str | None:
        """The ticket of the newest message with one of these e-mail ids."""
        ...

    async def set_email(
        self, tenant_id: str, message_id: str, *, email_message_id: str, from_address: str, to: Sequence[str]
    ) -> None: ...


class HistoryRepository(Protocol):
    async def add(self, entries: Sequence[HistoryEntry]) -> None: ...

    async def of_ticket(self, tenant_id: str, ticket_id: str) -> Sequence[HistoryEntry]:
        """Oldest first."""
        ...


class WatcherRepository(Protocol):
    async def watch(self, tenant_id: str, ticket_id: str, user_ids: Sequence[str]) -> None: ...

    async def unwatch(self, tenant_id: str, ticket_id: str, user_id: str) -> None: ...

    async def of_ticket(self, tenant_id: str, ticket_id: str) -> Sequence[str]: ...

    async def forget(self, tenant_id: str | None, user_id: str) -> None: ...


class LinkRepository(Protocol):
    async def link(self, tenant_id: str, link: Link) -> None:
        """Both directions; replaces an earlier link between the two."""
        ...

    async def unlink(self, tenant_id: str, ticket_id: str, other_id: str) -> None: ...

    async def of_ticket(self, tenant_id: str, ticket_id: str) -> Sequence[Link]: ...

    async def kind_between(self, tenant_id: str, ticket_id: str, other_id: str) -> LinkKind | None: ...


class TimeRepository(Protocol):
    async def add(self, entry: TimeEntry) -> None: ...

    async def of_ticket(self, tenant_id: str, ticket_id: str) -> Sequence[TimeEntry]: ...
