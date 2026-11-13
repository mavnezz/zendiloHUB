from dataclasses import dataclass
from datetime import datetime
from typing import Literal

type NotificationKind = Literal['assigned', 'mentioned', 'message', 'sla_breached']


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
