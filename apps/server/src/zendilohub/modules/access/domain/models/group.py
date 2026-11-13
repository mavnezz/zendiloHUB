from dataclasses import dataclass, field
from datetime import datetime

from .names import group_text

GROUPS_MAX = 200


@dataclass(kw_only=True)
class Group:
    """People who work together, e.g. "1st level" or "Technical team"; a person can be in several groups."""

    id: str
    tenant_id: str
    name: str
    description: str
    member_ids: frozenset[str] = field(default_factory=frozenset)
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(cls, *, id: str, tenant_id: str, name: str, description: str, now: datetime) -> Group:
        name, description = group_text(name, description)
        return cls(id=id, tenant_id=tenant_id, name=name, description=description, created_at=now, updated_at=now)

    def change(self, *, name: str, description: str, now: datetime) -> None:
        self.name, self.description = group_text(name, description)
        self.updated_at = now
