from dataclasses import dataclass
from datetime import datetime
from typing import Literal, get_args

from .ticket import Priority, TicketState

type TicketView = Literal['mine', 'unassigned', 'due', 'open', 'watching', 'closed', 'all']
"""
The ready-made lists of the inbox (like Zammad's overviews): `mine` open tickets the caller owns, `unassigned` open ones
nobody owns, `due` waiting ones whose date has come, `open` every open ticket, `watching` the ones the caller watches.
"""
TICKET_VIEWS: tuple[TicketView, ...] = get_args(TicketView.__value__)

type TicketSort = Literal['updated', 'created', 'priority', 'number', 'pending']
TICKET_SORTS: tuple[TicketSort, ...] = get_args(TicketSort.__value__)


@dataclass(frozen=True, kw_only=True)
class TicketFilter:
    tenant_id: str
    queue_ids: tuple[str, ...]
    """The queues the caller may see; nothing outside them is found."""
    user_id: str
    now: datetime
    view: TicketView = 'open'
    queue_id: str | None = None
    state: TicketState | None = None
    priority: Priority | None = None
    owner_id: str | None = None
    customer_ids: tuple[str, ...] | None = None
    ticket_ids: tuple[str, ...] | None = None
    tag: str | None = None
    query: str = ''
    sort: TicketSort = 'updated'
    descending: bool = True
    offset: int = 0
    limit: int = 50
