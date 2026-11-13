from ..domain.ports.repositories import MembershipRepository


class MembershipDirectory:
    """Tenancy's side of the `Memberships` contract: access asks it before putting someone in a group."""

    def __init__(self, memberships: MembershipRepository) -> None:
        self._memberships = memberships

    async def is_member(self, tenant_id: str, user_id: str) -> bool:
        return await self._memberships.find(tenant_id, user_id) is not None
