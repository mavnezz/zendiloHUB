from dataclasses import dataclass

from zendilohub.core.bus.message import Command
from zendilohub.core.domain.clock import Clock
from zendilohub.core.domain.email_address import normalized_email
from zendilohub.core.domain.id_generator import IdGenerator
from zendilohub.core.domain.permissions import Permission, TenantRole
from zendilohub.core.domain.rate_limited import TooManyRequestsError
from zendilohub.core.domain.rate_limiter import RateLimit, RateLimiter
from zendilohub.core.domain.transaction import TransactionManager

from ...domain.exceptions import (
    AlreadyMemberError,
    InvalidEmailError,
    InvalidInvitationError,
    InvitationForOtherEmailError,
    InvitationNotFoundError,
    OwnerOnlyError,
    TenantNotFoundError,
)
from ...domain.models.invitation import Invitation
from ...domain.models.membership import Membership
from ...domain.models.tenant import Tenant
from ...domain.ports.repositories import InvitationRepository, MembershipRepository, TenantRepository
from ...domain.ports.services import InvitationNotifier, TokenService
from ..services.roles import RoleBook

# Invitations are e-mails we send on request: nobody may use an organization to spam.
INVITATIONS_PER_TENANT = RateLimit('invitations-tenant', limit=50, window_seconds=60 * 60)


@dataclass(frozen=True, kw_only=True)
class InviteMember(Command[Invitation]):
    tenant_id: str
    actor_id: str
    actor_email: str
    actor_role: TenantRole
    actor_permissions: frozenset[Permission]
    email: str
    role: TenantRole
    link_base: str
    """The app's public URL; the link in the e-mail starts with it."""


class InviteMemberHandler:
    def __init__(
        self,
        tenants: TenantRepository,
        memberships: MembershipRepository,
        invitations: InvitationRepository,
        tokens: TokenService,
        notifier: InvitationNotifier,
        limiter: RateLimiter,
        ids: IdGenerator,
        clock: Clock,
        roles: RoleBook,
    ) -> None:
        self._roles = roles
        self._tenants = tenants
        self._memberships = memberships
        self._invitations = invitations
        self._tokens = tokens
        self._notifier = notifier
        self._limiter = limiter
        self._ids = ids
        self._clock = clock

    async def handle(self, command: InviteMember) -> Invitation:
        email = normalized_email(command.email)
        if email is None:
            raise InvalidEmailError()
        if command.role == 'owner' and command.actor_role != 'owner':
            raise OwnerOnlyError()
        await self._roles.check_assignable(command.tenant_id, command.role, command.actor_permissions)
        tenant = await self._tenants.find(command.tenant_id)
        if tenant is None:
            raise TenantNotFoundError()
        if await self._memberships.find_by_email(command.tenant_id, email) is not None:
            raise AlreadyMemberError()
        status = await self._limiter.hit(INVITATIONS_PER_TENANT, command.tenant_id)
        if not status.allowed:
            raise TooManyRequestsError(status.retry_after)

        now = self._clock.now()
        await self._invitations.delete_expired(now)
        issued = self._tokens.issue()
        invitation = Invitation.send(
            id=self._ids.new_id(),
            tenant_id=tenant.id,
            email=email,
            role=command.role,
            token_hash=issued.hash,
            invited_by=command.actor_id,
            now=now,
        )
        await self._invitations.save(invitation)
        await self._notifier.invite(
            invitation,
            tenant,
            inviter=command.actor_email,
            role_name=await self._roles.name_of(command.tenant_id, command.role),
            link=f'{command.link_base}/invitations?token={issued.token}',
        )
        return invitation


@dataclass(frozen=True, kw_only=True)
class RevokeInvitation(Command[Invitation]):
    tenant_id: str
    invitation_id: str


class RevokeInvitationHandler:
    def __init__(self, invitations: InvitationRepository) -> None:
        self._invitations = invitations

    async def handle(self, command: RevokeInvitation) -> Invitation:
        invitation = await self._invitations.find(command.tenant_id, command.invitation_id)
        if invitation is None:
            raise InvitationNotFoundError()
        await self._invitations.delete(command.invitation_id)
        return invitation


@dataclass(frozen=True, kw_only=True)
class AcceptInvitation(Command[Tenant]):
    token: str
    user_id: str
    email: str
    """The logged-in user's address; it must be the invited one."""


class AcceptInvitationHandler:
    def __init__(
        self,
        tenants: TenantRepository,
        memberships: MembershipRepository,
        invitations: InvitationRepository,
        tokens: TokenService,
        transactions: TransactionManager,
        clock: Clock,
    ) -> None:
        self._tenants = tenants
        self._memberships = memberships
        self._invitations = invitations
        self._tokens = tokens
        self._transactions = transactions
        self._clock = clock

    async def handle(self, command: AcceptInvitation) -> Tenant:
        now = self._clock.now()
        invitation = await self._invitations.find_by_token_hash(self._tokens.hash_of(command.token))
        if invitation is None or invitation.is_expired(now):
            raise InvalidInvitationError()
        if invitation.email != command.email:
            raise InvitationForOtherEmailError(invitation.email)
        tenant = await self._tenants.find(invitation.tenant_id)
        if tenant is None or not tenant.is_active:
            raise InvalidInvitationError()
        async with self._transactions.transaction():
            if await self._memberships.find(tenant.id, command.user_id) is None:
                await self._memberships.save(
                    Membership.join(
                        tenant_id=tenant.id, user_id=command.user_id, email=command.email, role=invitation.role, now=now
                    )
                )
            await self._invitations.delete(invitation.id)
        return tenant
