import hashlib
import secrets

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.domain.permissions import TenantRole
from zendilohub.core.http.access import ApiKeyAccess

from ..application.commands.api_keys import UseApiKey
from ..application.queries.tenants import RoleIn
from ..domain.ports.services import IssuedToken


class Sha256TokenService:
    """Random tokens; only their SHA-256 is stored, so a leaked database does not leak usable invitation links."""

    def issue(self) -> IssuedToken:
        token = secrets.token_urlsafe(32)
        return IssuedToken(token, self.hash_of(token))

    def hash_of(self, token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()


class TenantMembershipGuard:
    """Answers the HTTP kernel's question behind every tenant route: is this user a member, and with which role?"""

    def __init__(self, bus: CommandBus) -> None:
        self._bus = bus

    async def role_in(self, tenant_id: str, user_id: str) -> TenantRole | None:
        return await self._bus.query(RoleIn(tenant_id=tenant_id, user_id=user_id))


class TenantApiKeyGuard:
    """Answers the HTTP kernel's question for requests with an API key: which organization, which permissions?"""

    def __init__(self, bus: CommandBus) -> None:
        self._bus = bus

    async def authenticate_key(self, token: str) -> ApiKeyAccess | None:
        key = await self._bus.execute(UseApiKey(token))
        if key is None:
            return None
        return ApiKeyAccess(
            key_id=key.id, tenant_id=key.tenant_id, permissions=frozenset(key.permissions), name=key.name
        )
