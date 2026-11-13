from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ..models.audit_entry import AuditEntry


@dataclass(frozen=True)
class AuditPage:
    items: Sequence[AuditEntry]
    total: int


class AuditRepository(Protocol):
    async def add(self, entry: AuditEntry) -> None: ...

    async def page(self, *, tenant_id: str | None, offset: int, limit: int) -> AuditPage:
        """Newest first; `tenant_id` None means every entry (platform administration)."""
        ...

    async def delete_before(self, moment: datetime) -> int: ...

    async def delete_for_tenant(self, tenant_id: str) -> None: ...

    async def forget_actor(self, user_id: str, email: str) -> None:
        """Removes the e-mail address of a deleted account from its entries, also from those before its login (failed
        attempts); the pseudonymous id stays."""
        ...
