from collections.abc import Sequence
from dataclasses import dataclass

from zendilohub.core.bus.message import Command, Query
from zendilohub.core.domain.clock import Clock
from zendilohub.core.domain.id_generator import IdGenerator
from zendilohub.core.domain.permissions import Permission
from zendilohub.core.domain.transaction import TransactionManager

from ...domain.exceptions import (
    RoleExceedsOwnError,
    RoleInUseError,
    RoleLimitError,
    RoleNameTakenError,
    RoleNotFoundError,
)
from ...domain.models.role import ROLES_MAX, CustomRole
from ...domain.ports.repositories import RoleRepository


@dataclass(frozen=True, kw_only=True)
class CreateRole(Command[CustomRole]):
    tenant_id: str
    actor_permissions: frozenset[Permission]
    name: str
    description: str
    permissions: frozenset[Permission]


class CreateRoleHandler:
    def __init__(self, roles: RoleRepository, transactions: TransactionManager, ids: IdGenerator, clock: Clock) -> None:
        self._roles = roles
        self._transactions = transactions
        self._ids = ids
        self._clock = clock

    async def handle(self, command: CreateRole) -> CustomRole:
        role = CustomRole.create(
            id=self._ids.new_id(),
            tenant_id=command.tenant_id,
            name=command.name,
            description=command.description,
            permissions=command.permissions,
            now=self._clock.now(),
        )
        if not role.permissions <= command.actor_permissions:
            raise RoleExceedsOwnError()
        async with self._transactions.transaction():
            if await self._roles.count(command.tenant_id) >= ROLES_MAX:
                raise RoleLimitError(ROLES_MAX)
            if await self._roles.name_taken(command.tenant_id, role.name):
                raise RoleNameTakenError()
            await self._roles.save(role)
        return role


@dataclass(frozen=True, kw_only=True)
class UpdateRole(Command[CustomRole]):
    tenant_id: str
    actor_permissions: frozenset[Permission]
    role_id: str
    name: str
    description: str
    permissions: frozenset[Permission]


class UpdateRoleHandler:
    def __init__(self, roles: RoleRepository, transactions: TransactionManager, clock: Clock) -> None:
        self._roles = roles
        self._transactions = transactions
        self._clock = clock

    async def handle(self, command: UpdateRole) -> CustomRole:
        async with self._transactions.transaction():
            role = await self._roles.find(command.tenant_id, command.role_id)
            if role is None:
                raise RoleNotFoundError()
            # Neither widen a role beyond one's own permissions nor touch one that may do more.
            if not (role.permissions | command.permissions) <= command.actor_permissions:
                raise RoleExceedsOwnError()
            role.change(
                name=command.name,
                description=command.description,
                permissions=command.permissions,
                now=self._clock.now(),
            )
            if await self._roles.name_taken(command.tenant_id, role.name, except_id=role.id):
                raise RoleNameTakenError()
            await self._roles.save(role)
        return role


@dataclass(frozen=True, kw_only=True)
class DeleteRole(Command[CustomRole]):
    tenant_id: str
    actor_permissions: frozenset[Permission]
    role_id: str


class DeleteRoleHandler:
    def __init__(self, roles: RoleRepository, transactions: TransactionManager) -> None:
        self._roles = roles
        self._transactions = transactions

    async def handle(self, command: DeleteRole) -> CustomRole:
        async with self._transactions.transaction():
            role = await self._roles.find(command.tenant_id, command.role_id)
            if role is None:
                raise RoleNotFoundError()
            if not role.permissions <= command.actor_permissions:
                raise RoleExceedsOwnError()
            if await self._roles.in_use(command.tenant_id, role.id):
                raise RoleInUseError()
            await self._roles.delete(command.tenant_id, role.id)
        return role


@dataclass(frozen=True)
class RoleOverview:
    roles: Sequence[CustomRole]
    members: dict[str, int]
    """Members per role, built-in and own."""


@dataclass(frozen=True)
class ListRoles(Query[RoleOverview]):
    tenant_id: str


class ListRolesHandler:
    def __init__(self, roles: RoleRepository) -> None:
        self._roles = roles

    async def handle(self, query: ListRoles) -> RoleOverview:
        return RoleOverview(await self._roles.of_tenant(query.tenant_id), await self._roles.usage(query.tenant_id))
