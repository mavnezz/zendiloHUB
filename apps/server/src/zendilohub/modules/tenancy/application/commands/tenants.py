from dataclasses import dataclass

from zendilohub.core.bus.message import Command
from zendilohub.core.domain.clock import Clock
from zendilohub.core.domain.id_generator import IdGenerator
from zendilohub.core.domain.transaction import TransactionManager
from zendilohub.core.events.event_bus import EventBus
from zendilohub.core.events.integration_events import TenantCreated, TenantDeleted

from ...domain.exceptions import SingleOrganizationError, TenantNotFoundError
from ...domain.models.membership import Membership
from ...domain.models.tenant import Locale, Tenant, TenantStatus
from ...domain.ports.repositories import MembershipRepository, TenantRepository


@dataclass(frozen=True, kw_only=True)
class CreateTenant(Command[Tenant]):
    """A user creates an organization and becomes its owner."""

    user_id: str
    email: str
    name: str
    timezone: str
    locale: Locale


class CreateTenantHandler:
    """On a self-hosted instance only while there is no organization yet (the setup wizard's, or the first one)."""

    def __init__(
        self,
        tenants: TenantRepository,
        memberships: MembershipRepository,
        transactions: TransactionManager,
        events: EventBus,
        ids: IdGenerator,
        clock: Clock,
        *,
        self_hosted: bool = False,
    ) -> None:
        self._self_hosted = self_hosted
        self._tenants = tenants
        self._memberships = memberships
        self._transactions = transactions
        self._events = events
        self._ids = ids
        self._clock = clock

    async def handle(self, command: CreateTenant) -> Tenant:
        if self._self_hosted and await self._tenants.count() > 0:
            raise SingleOrganizationError()
        now = self._clock.now()
        tenant = Tenant.create(
            id=self._ids.new_id(), name=command.name, timezone=command.timezone, locale=command.locale, now=now
        )
        owner = Membership.join(
            tenant_id=tenant.id, user_id=command.user_id, email=command.email, role='owner', now=now
        )
        async with self._transactions.transaction():
            await self._tenants.save(tenant)
            await self._memberships.save(owner)
            await self._events.publish(TenantCreated(tenant_id=tenant.id, owner_id=command.user_id))
        return tenant


@dataclass(frozen=True, kw_only=True)
class UpdateTenant(Command[Tenant]):
    tenant_id: str
    name: str | None = None
    timezone: str | None = None
    locale: Locale | None = None


class UpdateTenantHandler:
    def __init__(self, tenants: TenantRepository, clock: Clock) -> None:
        self._tenants = tenants
        self._clock = clock

    async def handle(self, command: UpdateTenant) -> Tenant:
        tenant = await self._tenants.find(command.tenant_id)
        if tenant is None:
            raise TenantNotFoundError()
        tenant.update(name=command.name, timezone=command.timezone, locale=command.locale, now=self._clock.now())
        await self._tenants.save(tenant)
        return tenant


@dataclass(frozen=True)
class DeleteTenant(Command[None]):
    """Deletes the organization and, through the event, everything other modules keep for it."""

    tenant_id: str


class DeleteTenantHandler:
    def __init__(self, tenants: TenantRepository, transactions: TransactionManager, events: EventBus) -> None:
        self._tenants = tenants
        self._transactions = transactions
        self._events = events

    async def handle(self, command: DeleteTenant) -> None:
        async with self._transactions.transaction():
            await self._events.publish(TenantDeleted(tenant_id=command.tenant_id))
            await self._tenants.delete(command.tenant_id)


@dataclass(frozen=True)
class ChangeTenantStatus(Command[Tenant]):
    """Platform administrators suspend a tenant (e.g. unpaid, abuse) or reactivate it."""

    tenant_id: str
    status: TenantStatus


class ChangeTenantStatusHandler:
    def __init__(self, tenants: TenantRepository, clock: Clock) -> None:
        self._tenants = tenants
        self._clock = clock

    async def handle(self, command: ChangeTenantStatus) -> Tenant:
        tenant = await self._tenants.find(command.tenant_id)
        if tenant is None:
            raise TenantNotFoundError()
        tenant.change_status(command.status, self._clock.now())
        await self._tenants.save(tenant)
        return tenant
