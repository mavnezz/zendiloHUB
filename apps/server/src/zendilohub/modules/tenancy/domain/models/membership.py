from dataclasses import dataclass
from datetime import datetime

from zendilohub.core.domain.permissions import TenantRole

# Who takes over when the last owner leaves the platform: the most senior role first.
SENIORITY: tuple[TenantRole, ...] = ('owner', 'admin', 'manager', 'agent')


@dataclass(kw_only=True)
class Membership:
    """A user's place in a tenant. The e-mail address is a copy, so the member list needs no other module."""

    tenant_id: str
    user_id: str
    email: str
    role: TenantRole
    created_at: datetime
    updated_at: datetime

    @classmethod
    def join(cls, *, tenant_id: str, user_id: str, email: str, role: TenantRole, now: datetime) -> Membership:
        return cls(tenant_id=tenant_id, user_id=user_id, email=email, role=role, created_at=now, updated_at=now)

    @property
    def is_owner(self) -> bool:
        return self.role == 'owner'

    def change_role(self, role: TenantRole, now: datetime) -> None:
        self.role = role
        self.updated_at = now
