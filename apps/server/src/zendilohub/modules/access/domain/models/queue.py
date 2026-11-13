from dataclasses import dataclass
from datetime import datetime

from .names import queue_text

QUEUES_MAX = 200


@dataclass(kw_only=True)
class Queue:
    """Where tickets live, e.g. "Support" or "Billing". Who may do what in it, the groups' rights say."""

    id: str
    tenant_id: str
    name: str
    description: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(cls, *, id: str, tenant_id: str, name: str, description: str, now: datetime) -> Queue:
        name, description = queue_text(name, description)
        return cls(id=id, tenant_id=tenant_id, name=name, description=description, created_at=now, updated_at=now)

    def change(self, *, name: str, description: str, now: datetime) -> None:
        self.name, self.description = queue_text(name, description)
        self.updated_at = now
