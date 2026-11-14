from dataclasses import dataclass
from datetime import datetime
from typing import Literal, get_args

type NotificationKind = Literal['assigned', 'mentioned', 'message', 'sla_breached', 'created', 'moved']
"""`created`: a new ticket in a queue the member follows; `moved`: a ticket was moved into one."""
type FollowMode = Literal['new', 'all']
"""`new`: new tickets (and tickets moved into the queue); `all`: also every customer reply."""
FOLLOW_MODES: tuple[FollowMode, ...] = get_args(FollowMode.__value__)
FOLLOWED_MAX = 200


@dataclass(kw_only=True)
class Notification:
    """Something a member should know about a ticket: it went to them, they were mentioned, someone wrote in it."""

    id: str
    tenant_id: str
    user_id: str
    kind: NotificationKind
    ticket_id: str
    ticket_number: int
    subject: str
    actor: str
    """Who did it (an e-mail address, a customer, a rule)."""
    created_at: datetime
    read_at: datetime | None = None


@dataclass(kw_only=True)
class Settings:
    tenant_id: str
    user_id: str
    email: bool = False
    """Also by e-mail."""


@dataclass(frozen=True, kw_only=True)
class FollowedQueue:
    """A queue a member hears about, though its tickets are not theirs."""

    queue_id: str
    mode: FollowMode = 'new'
