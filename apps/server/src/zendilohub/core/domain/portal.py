"""What the portal and the tickets module hand each other (see the `TicketPortal` contract)."""

from dataclasses import dataclass, field
from datetime import datetime

from .files import FileInfo


@dataclass(frozen=True, kw_only=True)
class PortalTicket:
    """A ticket as its customer sees it: no queue, owner or internal notes."""

    id: str
    number: int
    subject: str
    state: str
    customer_id: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, kw_only=True)
class PortalMessage:
    id: str
    from_customer: bool
    author_name: str
    body: str
    created_at: datetime
    attachments: tuple[FileInfo, ...] = ()


@dataclass(frozen=True, kw_only=True)
class PortalThread:
    ticket: PortalTicket
    messages: list[PortalMessage] = field(default_factory=list)
