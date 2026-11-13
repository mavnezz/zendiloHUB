"""
What each role may do inside a tenant. Shared by all modules, so every module checks the same
matrix and the web app can show it (the role permissions page).
"""

from typing import Literal

type TenantRole = Literal['owner', 'admin', 'manager', 'agent']

TENANT_ROLES: tuple[TenantRole, ...] = ('owner', 'admin', 'manager', 'agent')

type Permission = Literal[
    'tenant.manage',
    'tenant.delete',
    'members.view',
    'members.manage',
    'members.assign_owner',
    'queues.manage',
    'queues.all',
    'integrations.manage',
    'audit.view',
]

_ALL: frozenset[TenantRole] = frozenset(TENANT_ROLES)
_ADMINS: frozenset[TenantRole] = frozenset({'owner', 'admin'})
_OWNER: frozenset[TenantRole] = frozenset({'owner'})

PERMISSIONS: dict[Permission, frozenset[TenantRole]] = {
    'tenant.manage': _ADMINS,
    'tenant.delete': _OWNER,
    'members.view': _ALL,
    'members.manage': _ADMINS,
    'members.assign_owner': _OWNER,
    # Queues, groups and the rights between them; seeing every queue's tickets is a right of its own.
    'queues.manage': _ADMINS,
    'queues.all': _OWNER,
    'integrations.manage': _ADMINS,
    'audit.view': _ADMINS,
}


def allows(role: TenantRole, permission: Permission) -> bool:
    return role in PERMISSIONS[permission]


def permissions_of(role: TenantRole) -> list[Permission]:
    return [permission for permission, roles in PERMISSIONS.items() if role in roles]
