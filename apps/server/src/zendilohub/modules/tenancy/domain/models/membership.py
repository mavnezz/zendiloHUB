from dataclasses import dataclass, field
from datetime import datetime

from zendilohub.core.domain.permissions import BUILTIN_ROLES, Permission, TenantRole, is_builtin, permissions_of

# Who takes over when the last owner leaves the platform: the most senior built-in role first, own roles last.
SENIORITY: tuple[TenantRole, ...] = BUILTIN_ROLES


def seniority(role: TenantRole) -> int:
    return SENIORITY.index(role) if role in SENIORITY else len(SENIORITY)


@dataclass(kw_only=True)
class Membership:
    """A user's place in a tenant. The e-mail address is a copy, so the member list needs no other module."""

    tenant_id: str
    user_id: str
    email: str
    role: TenantRole
    created_at: datetime
    updated_at: datetime
    role_permissions: frozenset[Permission] = field(default=frozenset(), compare=False)
    """What an own role allows, read along with the membership (built-in roles have theirs in the core)."""
    role_name: str | None = field(default=None, compare=False)
    """The name of an own role."""

    @classmethod
    def join(cls, *, tenant_id: str, user_id: str, email: str, role: TenantRole, now: datetime) -> Membership:
        return cls(tenant_id=tenant_id, user_id=user_id, email=email, role=role, created_at=now, updated_at=now)

    @property
    def is_owner(self) -> bool:
        return self.role == 'owner'

    @property
    def permissions(self) -> frozenset[Permission]:
        role = self.role
        return frozenset(permissions_of(role)) if is_builtin(role) else self.role_permissions

    def change_role(self, role: TenantRole, now: datetime) -> None:
        self.role = role
        self.updated_at = now
