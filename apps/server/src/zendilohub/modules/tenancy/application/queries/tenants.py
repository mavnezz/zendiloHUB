from collections.abc import Sequence
from dataclasses import dataclass

from zendilohub.core.bus.message import Query
from zendilohub.core.domain.permissions import TenantRole

from ...domain.exceptions import TenantNotFoundError
from ...domain.models.tenant import Tenant
from ...domain.ports.repositories import MembershipRepository, OwnTenant, TenantPage, TenantRepository


@dataclass(frozen=True)
class ListOwnTenants(Query[Sequence[OwnTenant]]):
    user_id: str


class ListOwnTenantsHandler:
    def __init__(self, memberships: MembershipRepository) -> None:
        self._memberships = memberships

    async def handle(self, query: ListOwnTenants) -> Sequence[OwnTenant]:
        return await self._memberships.of_user(query.user_id)


@dataclass(frozen=True)
class GetTenant(Query[Tenant]):
    tenant_id: str


class GetTenantHandler:
    def __init__(self, tenants: TenantRepository) -> None:
        self._tenants = tenants

    async def handle(self, query: GetTenant) -> Tenant:
        tenant = await self._tenants.find(query.tenant_id)
        if tenant is None:
            raise TenantNotFoundError()
        return tenant


@dataclass(frozen=True, kw_only=True)
class SearchTenants(Query[TenantPage]):
    query: str
    offset: int
    limit: int


class SearchTenantsHandler:
    def __init__(self, tenants: TenantRepository) -> None:
        self._tenants = tenants

    async def handle(self, query: SearchTenants) -> TenantPage:
        return await self._tenants.search(query.query, offset=query.offset, limit=query.limit)


@dataclass(frozen=True, kw_only=True)
class RoleIn(Query[TenantRole | None]):
    """The user's role in an active tenant (the HTTP policy of tenant routes)."""

    tenant_id: str
    user_id: str


class RoleInHandler:
    def __init__(self, memberships: MembershipRepository) -> None:
        self._memberships = memberships

    async def handle(self, query: RoleIn) -> TenantRole | None:
        membership = await self._memberships.role_in_active(query.tenant_id, query.user_id)
        return membership.role if membership else None
