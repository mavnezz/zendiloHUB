from zendilohub.core.contracts import MemberCard

from ..domain.ports.repositories import MembershipRepository, TenantRepository


class MembershipDirectory:
    """Tenancy's side of the `Memberships` contract."""

    def __init__(self, memberships: MembershipRepository) -> None:
        self._memberships = memberships

    async def is_member(self, tenant_id: str, user_id: str) -> bool:
        return await self._memberships.find(tenant_id, user_id) is not None

    async def members(self, tenant_id: str) -> list[MemberCard]:
        return [
            MemberCard(user_id=member.user_id, email=member.email, permissions=member.permissions)
            for member in await self._memberships.of_tenant(tenant_id)
        ]


class TenantNames:
    """Tenancy's side of the `OrganizationNames` contract."""

    def __init__(self, tenants: TenantRepository) -> None:
        self._tenants = tenants

    async def name_of(self, tenant_id: str) -> str | None:
        tenant = await self._tenants.find(tenant_id)
        return tenant.name if tenant else None

    async def timezone_of(self, tenant_id: str) -> str | None:
        tenant = await self._tenants.find(tenant_id)
        return tenant.timezone if tenant else None
