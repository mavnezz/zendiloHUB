from datetime import datetime

from pydantic import BaseModel

from ...domain.models.audit_entry import AuditEntry
from ...domain.ports.audit_repository import AuditPage


class AuditEntryResponse(BaseModel):
    id: str
    tenant_id: str | None
    actor_email: str | None
    """None for a deleted account or a request without one."""
    action: str
    target: str | None
    succeeded: bool
    status: int
    client: str | None
    created_at: datetime

    @classmethod
    def of(cls, entry: AuditEntry) -> AuditEntryResponse:
        return cls(
            id=entry.id,
            tenant_id=entry.tenant_id,
            actor_email=entry.actor_email,
            action=entry.action,
            target=entry.target,
            succeeded=entry.succeeded,
            status=entry.status,
            client=entry.client,
            created_at=entry.created_at,
        )


class AuditPageResponse(BaseModel):
    items: list[AuditEntryResponse]
    total: int

    @classmethod
    def of(cls, page: AuditPage) -> AuditPageResponse:
        return cls(items=[AuditEntryResponse.of(entry) for entry in page.items], total=page.total)
