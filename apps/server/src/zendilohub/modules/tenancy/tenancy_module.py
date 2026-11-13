from pathlib import Path

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.database.migration import sql_migrations
from zendilohub.core.events.integration_events import InstanceSetUp, UserDeleted
from zendilohub.core.module import AppModule, ModuleContext

from .application.commands.api_keys import (
    CreateApiKey,
    CreateApiKeyHandler,
    DeleteApiKey,
    DeleteApiKeyHandler,
    ListApiKeys,
    ListApiKeysHandler,
    UpdateApiKey,
    UpdateApiKeyHandler,
    UseApiKey,
    UseApiKeyHandler,
)
from .application.commands.invitations import (
    AcceptInvitation,
    AcceptInvitationHandler,
    InviteMember,
    InviteMemberHandler,
    RevokeInvitation,
    RevokeInvitationHandler,
)
from .application.commands.members import (
    ChangeMemberRole,
    ChangeMemberRoleHandler,
    ForgetUser,
    ForgetUserHandler,
    RemoveMember,
    RemoveMemberHandler,
)
from .application.commands.tenants import (
    ChangeTenantStatus,
    ChangeTenantStatusHandler,
    CreateTenant,
    CreateTenantHandler,
    DeleteTenant,
    DeleteTenantHandler,
    UpdateTenant,
    UpdateTenantHandler,
)
from .application.queries.members import (
    ListInvitations,
    ListInvitationsHandler,
    ListMembers,
    ListMembersHandler,
    PreviewInvitation,
    PreviewInvitationHandler,
)
from .application.queries.tenants import (
    GetTenant,
    GetTenantHandler,
    ListOwnTenants,
    ListOwnTenantsHandler,
    RoleIn,
    RoleInHandler,
    SearchTenants,
    SearchTenantsHandler,
)
from .domain.models.tenant import Locale
from .infrastructure.mail_notifier import MailInvitationNotifier
from .infrastructure.pending_invitations import PendingInvitations
from .infrastructure.postgres_api_keys import PostgresApiKeyRepository
from .infrastructure.postgres_tenancy import (
    PostgresInvitationRepository,
    PostgresMembershipRepository,
    PostgresTenantRepository,
)
from .infrastructure.security import Sha256TokenService, TenantApiKeyGuard, TenantMembershipGuard
from .ui.api.routes import admin_tenant_routes, invitation_routes, role_routes, tenant_routes

MIGRATIONS = Path(__file__).parent / 'infrastructure' / 'migrations'


def create_tenancy_module(context: ModuleContext) -> AppModule:
    """
    Organizations: the tenants of the platform, their members with roles, invitations, API keys. A self-hosted
    instance has one organization, made by the setup wizard.
    """
    db, clock, ids, events = context.db, context.clock, context.ids, context.events
    tenants = PostgresTenantRepository(db)
    memberships = PostgresMembershipRepository(db)
    invitations = PostgresInvitationRepository(db)
    api_keys = PostgresApiKeyRepository(db)
    tokens = Sha256TokenService()
    notifier = MailInvitationNotifier(context.mailer)

    bus = (
        CommandBus()
        .register(
            CreateTenant,
            CreateTenantHandler(
                tenants, memberships, db, events, ids, clock, self_hosted=not context.config.multi_tenant
            ),
        )
        .register(UpdateTenant, UpdateTenantHandler(tenants, clock))
        .register(DeleteTenant, DeleteTenantHandler(tenants, db, events))
        .register(ChangeTenantStatus, ChangeTenantStatusHandler(tenants, clock))
        .register(ChangeMemberRole, ChangeMemberRoleHandler(memberships, db, clock))
        .register(RemoveMember, RemoveMemberHandler(memberships, db, events))
        .register(ForgetUser, ForgetUserHandler(tenants, memberships, db, events, clock))
        .register(
            InviteMember,
            InviteMemberHandler(tenants, memberships, invitations, tokens, notifier, context.rate_limiter, ids, clock),
        )
        .register(RevokeInvitation, RevokeInvitationHandler(invitations))
        .register(AcceptInvitation, AcceptInvitationHandler(tenants, memberships, invitations, tokens, db, clock))
        .register(ListOwnTenants, ListOwnTenantsHandler(memberships))
        .register(GetTenant, GetTenantHandler(tenants))
        .register(SearchTenants, SearchTenantsHandler(tenants))
        .register(RoleIn, RoleInHandler(memberships))
        .register(ListMembers, ListMembersHandler(memberships))
        .register(ListInvitations, ListInvitationsHandler(invitations, clock))
        .register(PreviewInvitation, PreviewInvitationHandler(tenants, invitations, tokens, clock))
        .register(CreateApiKey, CreateApiKeyHandler(api_keys, ids, clock))
        .register(UpdateApiKey, UpdateApiKeyHandler(api_keys))
        .register(DeleteApiKey, DeleteApiKeyHandler(api_keys))
        .register(ListApiKeys, ListApiKeysHandler(api_keys))
        .register(UseApiKey, UseApiKeyHandler(api_keys, context.rate_limiter, clock))
    )
    guard = TenantMembershipGuard(bus)
    context.http.use_membership_guard(guard)
    context.http.use_api_key_guard(TenantApiKeyGuard(bus))

    async def forget(event: UserDeleted) -> None:
        await bus.execute(ForgetUser(event.user_id))

    context.events.subscribe(UserDeleted, forget)

    async def set_up(event: InstanceSetUp) -> None:
        locale: Locale = 'de' if event.locale == 'de' else 'en'
        await bus.execute(
            CreateTenant(
                user_id=event.user_id,
                email=event.email,
                name=event.organization_name,
                timezone=event.timezone,
                locale=locale,
            )
        )

    context.events.subscribe(InstanceSetUp, set_up)
    context.contracts.invitations.provide(PendingInvitations(invitations, clock))

    return AppModule(
        name='tenancy',
        migrations=sql_migrations(MIGRATIONS),
        routers=[tenant_routes(bus, context.config), invitation_routes(bus), role_routes(), admin_tenant_routes(bus)],
    )
