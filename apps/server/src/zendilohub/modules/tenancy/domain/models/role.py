from dataclasses import dataclass
from datetime import datetime

from zendilohub.core.domain.permissions import OWNER_ONLY, PERMISSIONS, Permission

from ..exceptions import InvalidRoleError

NAME_MAX = 80
DESCRIPTION_MAX = 500
ROLES_MAX = 50
"""Own roles per organization."""

ASSIGNABLE: frozenset[Permission] = frozenset(PERMISSIONS) - OWNER_ONLY
"""What an own role may hold: everything but what only owners may do."""


@dataclass(kw_only=True)
class CustomRole:
    """A role the organization made itself, e.g. "Team lead": its members get exactly these permissions."""

    id: str
    tenant_id: str
    name: str
    description: str
    permissions: frozenset[Permission]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        id: str,
        tenant_id: str,
        name: str,
        description: str,
        permissions: frozenset[Permission],
        now: datetime,
    ) -> CustomRole:
        role = cls(
            id=id,
            tenant_id=tenant_id,
            name='',
            description='',
            permissions=frozenset(),
            created_at=now,
            updated_at=now,
        )
        role.change(name=name, description=description, permissions=permissions, now=now)
        return role

    def change(self, *, name: str, description: str, permissions: frozenset[Permission], now: datetime) -> None:
        name, description = name.strip(), description.strip()
        if not name or len(name) > NAME_MAX:
            raise InvalidRoleError('name')
        if len(description) > DESCRIPTION_MAX:
            raise InvalidRoleError('description')
        if not permissions or not permissions <= ASSIGNABLE:
            raise InvalidRoleError('permissions')
        self.name, self.description, self.permissions, self.updated_at = name, description, permissions, now
