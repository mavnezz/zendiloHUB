from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ..models.api_key import ApiKey
from ..models.invitation import Invitation
from ..models.membership import Membership
from ..models.tenant import Tenant


@dataclass(frozen=True)
class TenantSummary:
    tenant: Tenant
    member_count: int


@dataclass(frozen=True)
class TenantPage:
    items: Sequence[TenantSummary]
    total: int


@dataclass(frozen=True)
class OwnTenant:
    """A tenant as one of its members sees it in the tenant switcher."""

    tenant: Tenant
    membership: Membership


class TenantRepository(Protocol):
    async def find(self, tenant_id: str) -> Tenant | None: ...

    async def count(self) -> int: ...

    async def save(self, tenant: Tenant) -> None: ...

    async def delete(self, tenant_id: str) -> None:
        """Deletes the tenant with its memberships and invitations."""
        ...

    async def search(self, query: str, *, offset: int, limit: int) -> TenantPage:
        """Tenants whose name contains `query`, newest first."""
        ...


class MembershipRepository(Protocol):
    async def find(self, tenant_id: str, user_id: str) -> Membership | None: ...

    async def find_by_email(self, tenant_id: str, email: str) -> Membership | None: ...

    async def of_tenant(self, tenant_id: str) -> Sequence[Membership]:
        """Oldest first."""
        ...

    async def of_user(self, user_id: str) -> Sequence[OwnTenant]:
        """The user's tenants with their membership, by name."""
        ...

    async def role_in_active(self, tenant_id: str, user_id: str) -> Membership | None:
        """The membership, if the tenant is active."""
        ...

    async def save(self, membership: Membership) -> None: ...

    async def delete(self, tenant_id: str, user_id: str) -> None: ...

    async def count_owners(self, tenant_id: str) -> int: ...


class InvitationRepository(Protocol):
    async def find(self, tenant_id: str, invitation_id: str) -> Invitation | None: ...

    async def find_by_token_hash(self, token_hash: str) -> Invitation | None: ...

    async def of_tenant(self, tenant_id: str) -> Sequence[Invitation]:
        """Newest first."""
        ...

    async def save(self, invitation: Invitation) -> None:
        """Replaces an earlier invitation of the same address to the same tenant."""
        ...

    async def delete(self, invitation_id: str) -> None: ...

    async def delete_expired(self, now: datetime) -> None: ...

    async def pending_for(self, email: str, now: datetime) -> bool:
        """Whether some organization invited the address and the invitation has not expired."""
        ...


class ApiKeyRepository(Protocol):
    async def keys(self, tenant_id: str) -> Sequence[ApiKey]:
        """Oldest first."""
        ...

    async def count(self, tenant_id: str) -> int: ...

    async def get(self, tenant_id: str, key_id: str) -> ApiKey | None: ...

    async def add(self, key: ApiKey, key_hash: str) -> None: ...

    async def update(self, key: ApiKey) -> None:
        """Its name and permissions."""
        ...

    async def delete(self, tenant_id: str, key_id: str) -> bool: ...

    async def active_by_hash(self, key_hash: str) -> ApiKey | None:
        """The key, if its organization is active."""
        ...

    async def touch(self, key_id: str, now: datetime) -> None: ...
