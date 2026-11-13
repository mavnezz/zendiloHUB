from dataclasses import dataclass
from datetime import datetime
from typing import Literal

type DeliveryStatus = Literal['queued', 'sent', 'failed', 'skipped']


@dataclass(kw_only=True)
class Delivery:
    """What became of a reply to the customer: sent, failed (with why), or skipped (no address, no account)."""

    message_id: str
    tenant_id: str
    ticket_id: str
    status: DeliveryStatus
    account_id: str | None
    error: str | None
    attempts: int
    updated_at: datetime


@dataclass(frozen=True, kw_only=True)
class FailedEmail:
    """A received e-mail that could not become a ticket; kept to look at and process again (like Zammad)."""

    id: str
    tenant_id: str
    account_id: str | None
    raw: bytes
    error: str
    received_at: datetime
