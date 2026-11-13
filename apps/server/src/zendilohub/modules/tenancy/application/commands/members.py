from dataclasses import dataclass

from zendilohub.core.bus.message import Command
from zendilohub.core.domain.clock import Clock
from zendilohub.core.domain.permissions import TenantRole
from zendilohub.core.domain.transaction import TransactionManager
from zendilohub.core.events.event_bus import EventBus
from zendilohub.core.events.integration_events import MemberRemoved, TenantDeleted

from ...domain.exceptions import LastOwnerError, MemberNotFoundError, OwnerOnlyError
from ...domain.models.membership import SENIORITY, Membership
from ...domain.ports.repositories import MembershipRepository, TenantRepository


@dataclass(frozen=True, kw_only=True)
class ChangeMemberRole(Command[Membership]):
    tenant_id: str
    actor_role: TenantRole
    user_id: str
    role: TenantRole


class ChangeMemberRoleHandler:
    def __init__(self, memberships: MembershipRepository, transactions: TransactionManager, clock: Clock) -> None:
        self._memberships = memberships
        self._transactions = transactions
        self._clock = clock

    async def handle(self, command: ChangeMemberRole) -> Membership:
        async with self._transactions.transaction():
            member = await self._memberships.find(command.tenant_id, command.user_id)
            if member is None:
                raise MemberNotFoundError()
            if (member.is_owner or command.role == 'owner') and command.actor_role != 'owner':
                raise OwnerOnlyError()
            if (
                member.is_owner
                and command.role != 'owner'
                and await self._memberships.count_owners(command.tenant_id) <= 1
            ):
                raise LastOwnerError()
            member.change_role(command.role, self._clock.now())
            await self._memberships.save(member)
        return member


@dataclass(frozen=True, kw_only=True)
class RemoveMember(Command[Membership]):
    """Removes someone from the tenant; members may also remove themselves (leave)."""

    tenant_id: str
    actor_id: str
    actor_role: TenantRole
    user_id: str


class RemoveMemberHandler:
    def __init__(self, memberships: MembershipRepository, transactions: TransactionManager, events: EventBus) -> None:
        self._memberships = memberships
        self._transactions = transactions
        self._events = events

    async def handle(self, command: RemoveMember) -> Membership:
        async with self._transactions.transaction():
            member = await self._memberships.find(command.tenant_id, command.user_id)
            if member is None:
                raise MemberNotFoundError()
            if member.is_owner and command.actor_role != 'owner':
                raise OwnerOnlyError()
            if member.is_owner and await self._memberships.count_owners(command.tenant_id) <= 1:
                raise LastOwnerError()
            await self._memberships.delete(command.tenant_id, command.user_id)
            await self._events.publish(MemberRemoved(tenant_id=command.tenant_id, user_id=command.user_id))
        return member


@dataclass(frozen=True)
class ForgetUser(Command[None]):
    """A user deleted their account: they leave every tenant. Tenants without members are deleted,
    tenants without an owner get the most senior remaining member as owner."""

    user_id: str


class ForgetUserHandler:
    def __init__(
        self,
        tenants: TenantRepository,
        memberships: MembershipRepository,
        transactions: TransactionManager,
        events: EventBus,
        clock: Clock,
    ) -> None:
        self._tenants = tenants
        self._memberships = memberships
        self._transactions = transactions
        self._events = events
        self._clock = clock

    async def handle(self, command: ForgetUser) -> None:
        async with self._transactions.transaction():
            for own in await self._memberships.of_user(command.user_id):
                tenant_id = own.tenant.id
                await self._memberships.delete(tenant_id, command.user_id)
                remaining = list(await self._memberships.of_tenant(tenant_id))
                if not remaining:
                    await self._events.publish(TenantDeleted(tenant_id=tenant_id))
                    await self._tenants.delete(tenant_id)
                elif not any(member.is_owner for member in remaining):
                    successor = min(remaining, key=lambda member: (SENIORITY.index(member.role), member.created_at))
                    successor.change_role('owner', self._clock.now())
                    await self._memberships.save(successor)
