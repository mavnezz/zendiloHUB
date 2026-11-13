import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, get_args

from ..exceptions import InvalidTicketError

type TicketState = Literal['new', 'open', 'pending_reminder', 'pending_close', 'closed', 'merged']
"""
`new` until someone works on it; `pending_reminder` comes back on its date (the "due" view), `pending_close` closes
itself on its date (both like OTOBO); `merged` tickets live on in the one they were merged into.
"""
TICKET_STATES: tuple[TicketState, ...] = get_args(TicketState.__value__)
OPEN_STATES: tuple[TicketState, ...] = ('new', 'open', 'pending_reminder', 'pending_close')
PENDING_STATES: tuple[TicketState, ...] = ('pending_reminder', 'pending_close')
SETTABLE_STATES: tuple[TicketState, ...] = ('new', 'open', 'pending_reminder', 'pending_close', 'closed')

type Priority = Literal['low', 'normal', 'high', 'urgent']
PRIORITIES: tuple[Priority, ...] = get_args(Priority.__value__)

type Channel = Literal['web', 'email', 'phone', 'api']
CHANNELS: tuple[Channel, ...] = get_args(Channel.__value__)

SUBJECT_MAX = 250
TAGS_MAX = 30
TAG_MAX = 50
_TAG = re.compile(r'^[\w][\w .&+/-]*$')


def clean_subject(raw: str) -> str:
    subject = ' '.join(raw.split())
    if not 1 <= len(subject) <= SUBJECT_MAX:
        raise InvalidTicketError('subject')
    return subject


def clean_tags(raw: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    """Lower case, trimmed, without duplicates, sorted."""
    tags = {' '.join(tag.split()).lower() for tag in raw if tag.strip()}
    if len(tags) > TAGS_MAX or any(len(tag) > TAG_MAX or not _TAG.match(tag) for tag in tags):
        raise InvalidTicketError('tags')
    return tuple(sorted(tags))


@dataclass(frozen=True)
class Change:
    """One field of a ticket changed; the history keeps it."""

    field: str
    old: str | None
    new: str | None


def _text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return ', '.join(str(each) for each in value) or None
    return str(value)


@dataclass(kw_only=True)
class Ticket:
    """A customer's concern: it lies in one queue and collects the messages about it."""

    id: str
    tenant_id: str
    number: int
    subject: str
    queue_id: str
    state: TicketState
    priority: Priority
    channel: Channel
    customer_id: str | None
    owner_id: str | None
    responsible_id: str | None
    tags: tuple[str, ...]
    pending_until: datetime | None
    merged_into_id: str | None
    created_at: datetime
    updated_at: datetime
    first_response_at: datetime | None = None
    closed_at: datetime | None = None
    last_message_at: datetime | None = None
    changes: list[Change] = field(default_factory=list, compare=False, repr=False)
    """What the last calls changed, for the history; the repository does not store it."""

    @classmethod
    def open(
        cls,
        *,
        id: str,
        tenant_id: str,
        number: int,
        subject: str,
        queue_id: str,
        channel: Channel,
        customer_id: str | None,
        priority: Priority,
        tags: tuple[str, ...],
        now: datetime,
    ) -> Ticket:
        return cls(
            id=id,
            tenant_id=tenant_id,
            number=number,
            subject=clean_subject(subject),
            queue_id=queue_id,
            state='new',
            priority=priority,
            channel=channel,
            customer_id=customer_id,
            owner_id=None,
            responsible_id=None,
            tags=clean_tags(tags),
            pending_until=None,
            merged_into_id=None,
            created_at=now,
            updated_at=now,
            last_message_at=None,
        )

    @property
    def is_open(self) -> bool:
        return self.state in OPEN_STATES

    @property
    def is_merged(self) -> bool:
        return self.state == 'merged'

    def _set(self, name: str, value: object, now: datetime) -> None:
        old = getattr(self, name)
        if old == value:
            return
        setattr(self, name, value)
        self.changes.append(Change(name, _text(old), _text(value)))
        self.updated_at = now

    def rename(self, subject: str, now: datetime) -> None:
        self._set('subject', clean_subject(subject), now)

    def set_state(self, state: TicketState, now: datetime, *, pending_until: datetime | None = None) -> None:
        """Pending states need the date they end; other states clear it."""
        if state not in SETTABLE_STATES:
            raise InvalidTicketError('state')
        if state in PENDING_STATES and pending_until is None:
            raise InvalidTicketError('pending_until')
        self._set('state', state, now)
        self._set('pending_until', pending_until if state in PENDING_STATES else None, now)
        if state == 'closed' and self.closed_at is None:
            self.closed_at = now
        elif state != 'closed':
            self.closed_at = None

    def set_priority(self, priority: Priority, now: datetime) -> None:
        self._set('priority', priority, now)

    def assign(self, owner_id: str | None, now: datetime) -> None:
        self._set('owner_id', owner_id, now)

    def make_responsible(self, user_id: str | None, now: datetime) -> None:
        self._set('responsible_id', user_id, now)

    def move(self, queue_id: str, now: datetime) -> None:
        self._set('queue_id', queue_id, now)

    def retag(self, tags: list[str] | tuple[str, ...], now: datetime) -> None:
        self._set('tags', clean_tags(tags), now)

    def change_customer(self, customer_id: str | None, now: datetime) -> None:
        self._set('customer_id', customer_id, now)

    def received(self, now: datetime) -> None:
        """The customer wrote: a ticket that waited or was closed is open again."""
        self.last_message_at = now
        if self.state in ('pending_reminder', 'pending_close', 'closed'):
            self.set_state('open', now)
        self.updated_at = now

    def answered(self, now: datetime) -> None:
        """An agent replied to the customer."""
        self.last_message_at = now
        if self.first_response_at is None:
            self.first_response_at = now
        if self.state == 'new':
            self.set_state('open', now)
        self.updated_at = now

    def noted(self, now: datetime) -> None:
        self.updated_at = now

    def merge_into(self, target: Ticket, now: datetime) -> None:
        self._set('state', 'merged', now)
        self._set('merged_into_id', target.id, now)
        self.pending_until = None
        self.closed_at = now
