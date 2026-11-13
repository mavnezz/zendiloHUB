from zendilohub.core.domain.permissions import Permission, TenantRole, is_builtin, permissions_of

from ...domain.exceptions import RoleExceedsOwnError, RoleNotFoundError
from ...domain.ports.repositories import RoleRepository


class RoleBook:
    """What a role allows, built-in or the organization's own, and who may hand it out."""

    def __init__(self, roles: RoleRepository) -> None:
        self._roles = roles

    async def permissions_of(self, tenant_id: str, role: TenantRole) -> frozenset[Permission]:
        if is_builtin(role):
            return frozenset(permissions_of(role))
        custom = await self._roles.find(tenant_id, role) if _uuid_like(role) else None
        if custom is None:
            raise RoleNotFoundError()
        return custom.permissions

    async def name_of(self, tenant_id: str, role: TenantRole) -> str | None:
        """The name of an own role; None for built-in roles (their names are translated)."""
        if is_builtin(role):
            return None
        custom = await self._roles.find(tenant_id, role) if _uuid_like(role) else None
        return custom.name if custom else None

    async def check_assignable(self, tenant_id: str, role: TenantRole, actor: frozenset[Permission]) -> None:
        """Nobody hands out a role that may do more than they may themselves."""
        if not await self.permissions_of(tenant_id, role) <= actor:
            raise RoleExceedsOwnError()


def _uuid_like(text: str) -> bool:
    return len(text) == 36 and text.count('-') == 4
