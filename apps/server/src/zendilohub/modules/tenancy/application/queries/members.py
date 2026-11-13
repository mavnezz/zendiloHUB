from collections.abc import Sequence
from dataclasses import dataclass

from zendilohub.core.bus.message import Query
from zendilohub.core.domain.clock import Clock

from ...domain.exceptions import InvalidInvitationError
from ...domain.models.invitation import Invitation
from ...domain.models.membership import Membership
from ...domain.models.tenant import Tenant
from ...domain.ports.repositories import InvitationRepository, MembershipRepository, TenantRepository
from ...domain.ports.services import TokenService
from ..services.roles import RoleBook


@dataclass(frozen=True)
class ListMembers(Query[Sequence[Membership]]):
    tenant_id: str


class ListMembersHandler:
    def __init__(self, memberships: MembershipRepository) -> None:
        self._memberships = memberships

    async def handle(self, query: ListMembers) -> Sequence[Membership]:
        return await self._memberships.of_tenant(query.tenant_id)


@dataclass(frozen=True)
class ListInvitations(Query[Sequence[Invitation]]):
    tenant_id: str


class ListInvitationsHandler:
    def __init__(self, invitations: InvitationRepository, clock: Clock) -> None:
        self._invitations = invitations
        self._clock = clock

    async def handle(self, query: ListInvitations) -> Sequence[Invitation]:
        await self._invitations.delete_expired(self._clock.now())
        return await self._invitations.of_tenant(query.tenant_id)


@dataclass(frozen=True)
class InvitationPreview:
    invitation: Invitation
    tenant: Tenant
    role_name: str | None = None
    """The name of an own role."""


@dataclass(frozen=True)
class PreviewInvitation(Query[InvitationPreview]):
    """What the invitation page shows before the invited person accepts."""

    token: str


class PreviewInvitationHandler:
    def __init__(
        self,
        tenants: TenantRepository,
        invitations: InvitationRepository,
        tokens: TokenService,
        clock: Clock,
        roles: RoleBook,
    ) -> None:
        self._roles = roles
        self._tenants = tenants
        self._invitations = invitations
        self._tokens = tokens
        self._clock = clock

    async def handle(self, query: PreviewInvitation) -> InvitationPreview:
        invitation = await self._invitations.find_by_token_hash(self._tokens.hash_of(query.token))
        if invitation is None or invitation.is_expired(self._clock.now()):
            raise InvalidInvitationError()
        tenant = await self._tenants.find(invitation.tenant_id)
        if tenant is None or not tenant.is_active:
            raise InvalidInvitationError()
        return InvitationPreview(invitation, tenant, await self._roles.name_of(tenant.id, invitation.role))
