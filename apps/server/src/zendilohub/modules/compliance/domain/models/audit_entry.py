from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, kw_only=True)
class AuditEntry:
    """One change made through the API, or an attempt at it. Entries are never edited, only purged after the
    retention period (and stripped of the e-mail address when the account is deleted)."""

    id: str
    tenant_id: str | None
    actor_id: str | None
    actor_email: str | None
    action: str
    target: str | None
    succeeded: bool
    status: int
    client: str | None
    created_at: datetime
