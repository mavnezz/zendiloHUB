from dataclasses import dataclass

from zendilohub.core.bus.message import Query

from ...domain.ports.audit_repository import AuditPage, AuditRepository


@dataclass(frozen=True, kw_only=True)
class ListAuditLog(Query[AuditPage]):
    tenant_id: str | None
    """None: every entry (platform administration)."""
    offset: int
    limit: int


class ListAuditLogHandler:
    def __init__(self, entries: AuditRepository) -> None:
        self._entries = entries

    async def handle(self, query: ListAuditLog) -> AuditPage:
        return await self._entries.page(tenant_id=query.tenant_id, offset=query.offset, limit=query.limit)
