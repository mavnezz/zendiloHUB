"""
What members may do inside a tenant. Shared by all modules, so every module checks the same
permissions and the web app can show them (the roles page).

A member has one role: one of the built-in roles below, or a role the organization made itself (its id), which holds
any permissions except those only owners have.
"""

from dataclasses import dataclass
from typing import Literal, TypeGuard

type BuiltinRole = Literal['owner', 'admin', 'manager', 'agent']

type TenantRole = str
"""A built-in role, or the id of one of the organization's own roles."""

BUILTIN_ROLES: tuple[BuiltinRole, ...] = ('owner', 'admin', 'manager', 'agent')

type Permission = Literal[
    'tenant.manage',
    'tenant.delete',
    'members.view',
    'members.manage',
    'members.assign_owner',
    'queues.manage',
    'queues.all',
    'tickets.delete',
    'customers.view',
    'customers.manage',
    'channels.manage',
    'automation.manage',
    'knowledge.manage',
    'service.manage',
    'reports.view',
    'integrations.manage',
    'audit.view',
]

_ALL: frozenset[BuiltinRole] = frozenset(BUILTIN_ROLES)
_ADMINS: frozenset[BuiltinRole] = frozenset({'owner', 'admin'})
_OWNER: frozenset[BuiltinRole] = frozenset({'owner'})
_MANAGERS: frozenset[BuiltinRole] = frozenset({'owner', 'admin', 'manager'})

PERMISSIONS: dict[Permission, frozenset[BuiltinRole]] = {
    'tenant.manage': _ADMINS,
    'tenant.delete': _OWNER,
    'members.view': _ALL,
    'members.manage': _ADMINS,
    'members.assign_owner': _OWNER,
    # Queues, groups and the rights between them; seeing every queue's tickets is a right of its own.
    'queues.manage': _ADMINS,
    'queues.all': _OWNER,
    # What someone may do with a ticket comes from their groups' rights in its queue; deleting is a permission on top.
    'tickets.delete': _ADMINS,
    'customers.view': _ALL,
    'customers.manage': _ALL,
    # E-mail accounts, signatures, auto replies, filters.
    'channels.manage': _ADMINS,
    # Macros, triggers and scheduled jobs; text modules and the knowledge base.
    'automation.manage': _ADMINS,
    'knowledge.manage': _MANAGERS,
    # Service levels (response and solution times, business hours); reports on the tickets of every queue.
    'service.manage': _ADMINS,
    'reports.view': _MANAGERS,
    'integrations.manage': _ADMINS,
    'audit.view': _ADMINS,
}

OWNER_ONLY: frozenset[Permission] = frozenset({'tenant.delete', 'members.assign_owner'})
"""What no role but the owner's may hold: deleting the organization and making owners."""


def is_builtin(role: TenantRole) -> TypeGuard[BuiltinRole]:
    return role in BUILTIN_ROLES


def allows(role: BuiltinRole, permission: Permission) -> bool:
    return role in PERMISSIONS[permission]


def permissions_of(role: BuiltinRole) -> list[Permission]:
    return [permission for permission, roles in PERMISSIONS.items() if role in roles]


def ordered(permissions: frozenset[Permission] | set[Permission]) -> list[Permission]:
    """In the order of PERMISSIONS, for stable answers."""
    return [permission for permission in PERMISSIONS if permission in permissions]


@dataclass(frozen=True, kw_only=True)
class MemberRole:
    """A member's role in a tenant and what it allows."""

    role: TenantRole
    permissions: frozenset[Permission]
