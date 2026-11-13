"""What automation (triggers, scheduled jobs) and the tickets module hand each other (see `TicketAutomation`)."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, kw_only=True)
class TicketFacts:
    """A ticket as rules see it."""

    id: str
    number: int
    subject: str
    queue_id: str
    state: str
    priority: str
    channel: str
    tags: tuple[str, ...]
    owner_id: str | None
    responsible_id: str | None
    customer_id: str | None
    customer_email: str | None
    watchers: tuple[str, ...]
    created_at: datetime
    updated_at: datetime
    pending_until: datetime | None
    last_message_at: datetime | None
    fields: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class TicketCriteria:
    """Which tickets a scheduled job works on (all given conditions must hold)."""

    states: tuple[str, ...] = ()
    queue_ids: tuple[str, ...] = ()
    priorities: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    """Tickets with all these tags."""
    owner: str = 'any'
    """`any`, `none` (unassigned) or `set`."""
    updated_before: datetime | None = None
    created_before: datetime | None = None
    pending_passed: bool = False
    limit: int = 500


@dataclass(frozen=True, kw_only=True)
class AutomationChanges:
    """What a rule does to a ticket; empty fields leave it as it is."""

    state: str | None = None
    pending_hours: int | None = None
    """For a pending state: until this many hours from now."""
    priority: str | None = None
    queue_id: str | None = None
    owner_id: str | None = None
    unassign: bool = False
    add_tags: tuple[str, ...] = ()
    remove_tags: tuple[str, ...] = ()
    note: str | None = None
    """An internal note."""
    reply: str | None = None
    """A message to the customer (sent by e-mail when the queue has an account)."""
