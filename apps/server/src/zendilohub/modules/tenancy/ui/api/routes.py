from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.config import AppConfig
from zendilohub.core.domain.permissions import permissions_of
from zendilohub.core.http.access import (
    CurrentAdmin,
    CurrentMember,
    CurrentPerson,
    CurrentUser,
    Member,
    Public,
    member_with,
)
from zendilohub.core.http.audit import Unaudited, audited, note_audit
from zendilohub.core.http.ids import Id

from ...application.commands.api_keys import CreateApiKey, DeleteApiKey, ListApiKeys, UpdateApiKey
from ...application.commands.invitations import AcceptInvitation, InviteMember, RevokeInvitation
from ...application.commands.members import ChangeMemberRole, RemoveMember
from ...application.commands.roles import CreateRole, DeleteRole, ListRoles, UpdateRole
from ...application.commands.tenants import ChangeTenantStatus, CreateTenant, DeleteTenant, UpdateTenant
from ...application.queries.members import ListInvitations, ListMembers, PreviewInvitation
from ...application.queries.tenants import GetTenant, ListOwnTenants, SearchTenants
from ...domain.exceptions import RoleExceedsOwnError
from ...domain.models.api_key import KeyPermission
from .schemas import (
    AdminTenantPageResponse,
    ApiKeyRequest,
    ApiKeyResponse,
    ChangeRoleRequest,
    ChangeStatusRequest,
    CreatedApiKeyResponse,
    CreateTenantRequest,
    InvitationPreviewResponse,
    InvitationResponse,
    InviteRequest,
    MemberResponse,
    OwnTenantResponse,
    RoleRequest,
    RoleResponse,
    RolesResponse,
    TenantResponse,
    TokenRequest,
    UpdateTenantRequest,
)


def tenant_routes(bus: CommandBus, config: AppConfig) -> APIRouter:
    router = APIRouter(prefix='/tenants', tags=['tenants'])

    @router.get('')
    async def index(principal: CurrentUser) -> list[OwnTenantResponse]:
        """The caller's organizations, with their role in each."""
        return [OwnTenantResponse.of_own(own) for own in await bus.query(ListOwnTenants(principal.user_id))]

    @router.post('', status_code=201, dependencies=[audited('tenant.created')])
    async def create(body: CreateTenantRequest, request: Request, principal: CurrentUser) -> OwnTenantResponse:
        """Creates an organization; the caller becomes its owner."""
        tenant = await bus.execute(
            CreateTenant(
                user_id=principal.user_id,
                email=principal.email,
                name=body.name,
                timezone=body.timezone,
                locale=body.locale,
            )
        )
        note_audit(request, tenant_id=tenant.id, target=tenant.name)
        return OwnTenantResponse.of_role(tenant, 'owner', frozenset(permissions_of('owner')))

    @router.get('/{tenant_id}')
    async def show(member: CurrentMember) -> OwnTenantResponse:
        return OwnTenantResponse.of_member(await bus.query(GetTenant(member.tenant_id)), member)

    @router.patch('/{tenant_id}', dependencies=[audited('tenant.updated')])
    async def update(
        body: UpdateTenantRequest, member: Annotated[Member, member_with('tenant.manage', people_only=True)]
    ) -> OwnTenantResponse:
        tenant = await bus.execute(
            UpdateTenant(tenant_id=member.tenant_id, name=body.name, timezone=body.timezone, locale=body.locale)
        )
        return OwnTenantResponse.of_member(tenant, member)

    @router.delete('/{tenant_id}', status_code=204, response_class=Response, dependencies=[audited('tenant.deleted')])
    async def destroy(member: Annotated[Member, member_with('tenant.delete', people_only=True)]) -> None:
        """Deletes the organization with all its data."""
        await bus.execute(DeleteTenant(member.tenant_id))

    @router.get('/{tenant_id}/members')
    async def members(member: Annotated[Member, member_with('members.view')]) -> list[MemberResponse]:
        return [MemberResponse.of(each) for each in await bus.query(ListMembers(member.tenant_id))]

    @router.patch('/{tenant_id}/members/{user_id}', dependencies=[audited('member.role_changed')])
    async def change_role(
        user_id: Id,
        body: ChangeRoleRequest,
        request: Request,
        member: Annotated[Member, member_with('members.manage', people_only=True)],
    ) -> MemberResponse:
        changed = await bus.execute(
            ChangeMemberRole(
                tenant_id=member.tenant_id,
                actor_role=member.person_role,
                actor_permissions=member.permissions,
                user_id=user_id,
                role=body.role,
            )
        )
        note_audit(request, target=f'{changed.email}: {changed.role}')
        return MemberResponse.of(changed)

    @router.delete(
        '/{tenant_id}/members/{user_id}',
        status_code=204,
        response_class=Response,
        dependencies=[audited('member.removed')],
    )
    async def remove(user_id: Id, request: Request, member: CurrentPerson) -> None:
        """Removes a member; everyone may remove themselves (leave the organization)."""
        if user_id != member.user_id:
            member.require('members.manage')
        removed = await bus.execute(
            RemoveMember(
                tenant_id=member.tenant_id,
                actor_id=member.user_id,
                actor_role=member.person_role,
                actor_permissions=member.permissions,
                user_id=user_id,
            )
        )
        note_audit(request, target=removed.email)

    @router.get('/{tenant_id}/invitations')
    async def invitations(
        member: Annotated[Member, member_with('members.manage', people_only=True)],
    ) -> list[InvitationResponse]:
        return [InvitationResponse.of(each) for each in await bus.query(ListInvitations(member.tenant_id))]

    @router.post('/{tenant_id}/invitations', status_code=201, dependencies=[audited('invitation.sent')])
    async def invite(
        body: InviteRequest,
        request: Request,
        member: Annotated[Member, member_with('members.manage', people_only=True)],
    ) -> InvitationResponse:
        """Sends an invitation by e-mail; inviting the same address again replaces the earlier invitation."""
        invitation = await bus.execute(
            InviteMember(
                tenant_id=member.tenant_id,
                actor_id=member.user_id,
                actor_email=member.principal.email,
                actor_role=member.person_role,
                actor_permissions=member.permissions,
                email=body.email,
                role=body.role,
                link_base=config.public_url or str(request.base_url).rstrip('/'),
            )
        )
        note_audit(request, target=f'{invitation.email}: {invitation.role}')
        return InvitationResponse.of(invitation)

    @router.delete(
        '/{tenant_id}/invitations/{invitation_id}',
        status_code=204,
        response_class=Response,
        dependencies=[audited('invitation.revoked')],
    )
    async def revoke(
        invitation_id: Id, request: Request, member: Annotated[Member, member_with('members.manage', people_only=True)]
    ) -> None:
        revoked = await bus.execute(RevokeInvitation(tenant_id=member.tenant_id, invitation_id=invitation_id))
        note_audit(request, target=revoked.email)

    @router.get('/{tenant_id}/roles')
    async def roles(member: CurrentMember) -> RolesResponse:
        """Every role with what it allows and how many members have it (the roles page)."""
        return RolesResponse.of(await bus.query(ListRoles(member.tenant_id)))

    @router.post('/{tenant_id}/roles', status_code=201, dependencies=[audited('role.created')])
    async def create_role(
        body: RoleRequest, request: Request, member: Annotated[Member, member_with('members.manage', people_only=True)]
    ) -> RoleResponse:
        """A role of the organization's own; it may hold only what the caller may do."""
        role = await bus.execute(
            CreateRole(
                tenant_id=member.tenant_id,
                actor_permissions=member.permissions,
                name=body.name,
                description=body.description,
                permissions=frozenset(body.permissions),
            )
        )
        note_audit(request, target=role.name)
        return RoleResponse.of(role, 0)

    @router.patch('/{tenant_id}/roles/{role_id}', dependencies=[audited('role.updated')])
    async def update_role(
        role_id: Id,
        body: RoleRequest,
        request: Request,
        member: Annotated[Member, member_with('members.manage', people_only=True)],
    ) -> RoleResponse:
        role = await bus.execute(
            UpdateRole(
                tenant_id=member.tenant_id,
                actor_permissions=member.permissions,
                role_id=role_id,
                name=body.name,
                description=body.description,
                permissions=frozenset(body.permissions),
            )
        )
        note_audit(request, target=role.name)
        overview = await bus.query(ListRoles(member.tenant_id))
        return RoleResponse.of(role, overview.members.get(role.id, 0))

    @router.delete(
        '/{tenant_id}/roles/{role_id}', status_code=204, response_class=Response, dependencies=[audited('role.deleted')]
    )
    async def delete_role(
        role_id: Id, request: Request, member: Annotated[Member, member_with('members.manage', people_only=True)]
    ) -> None:
        """Only roles nobody has any more (members or invitations)."""
        role = await bus.execute(
            DeleteRole(tenant_id=member.tenant_id, actor_permissions=member.permissions, role_id=role_id)
        )
        note_audit(request, target=role.name)

    @router.get('/{tenant_id}/api-keys')
    async def api_keys(
        member: Annotated[Member, member_with('integrations.manage', people_only=True)],
    ) -> list[ApiKeyResponse]:
        """The organization's API keys, without the keys themselves."""
        return [ApiKeyResponse.of(key) for key in await bus.query(ListApiKeys(member.tenant_id))]

    @router.post('/{tenant_id}/api-keys', status_code=201, dependencies=[audited('api_key.created')])
    async def create_api_key(
        body: ApiKeyRequest,
        request: Request,
        member: Annotated[Member, member_with('integrations.manage', people_only=True)],
    ) -> CreatedApiKeyResponse:
        """A new key with its permissions (only what the caller may do); the key is in this answer only."""
        _within_own(member, body.permissions)
        created = await bus.execute(CreateApiKey(member.tenant_id, body.name, tuple(body.permissions), member.user_id))
        note_audit(request, target=created.key.name)
        return CreatedApiKeyResponse.of(created)

    @router.patch('/{tenant_id}/api-keys/{key_id}', dependencies=[audited('api_key.updated')])
    async def update_api_key(
        key_id: Id,
        body: ApiKeyRequest,
        request: Request,
        member: Annotated[Member, member_with('integrations.manage', people_only=True)],
    ) -> ApiKeyResponse:
        """Another name or other permissions; they apply to the key at once."""
        _within_own(member, body.permissions)
        key = await bus.execute(UpdateApiKey(member.tenant_id, key_id, body.name, tuple(body.permissions)))
        note_audit(request, target=key.name)
        return ApiKeyResponse.of(key)

    @router.delete(
        '/{tenant_id}/api-keys/{key_id}',
        status_code=204,
        response_class=Response,
        dependencies=[audited('api_key.deleted')],
    )
    async def delete_api_key(
        key_id: Id, member: Annotated[Member, member_with('integrations.manage', people_only=True)]
    ) -> None:
        """The key stops working at once."""
        await bus.execute(DeleteApiKey(member.tenant_id, key_id))

    return router


def _within_own(member: Member, permissions: list[KeyPermission]) -> None:
    """Nobody makes a key that may do more than they may."""
    if not set(permissions) <= member.permissions:
        raise RoleExceedsOwnError()


def invitation_routes(bus: CommandBus) -> APIRouter:
    router = APIRouter(prefix='/invitations', tags=['tenants'])

    @router.post('/preview', dependencies=[Public, Unaudited])
    async def preview(body: TokenRequest) -> InvitationPreviewResponse:
        """Who invites to what (the token is the secret from the e-mail link)."""
        return InvitationPreviewResponse.of(await bus.query(PreviewInvitation(body.token)))

    @router.post('/accept', dependencies=[audited('invitation.accepted')])
    async def accept(body: TokenRequest, request: Request, principal: CurrentUser) -> OwnTenantResponse:
        """Joins the organization; only the account with the invited e-mail address can accept."""
        tenant = await bus.execute(AcceptInvitation(token=body.token, user_id=principal.user_id, email=principal.email))
        note_audit(request, tenant_id=tenant.id, target=principal.email)
        return await _own(bus, tenant.id, principal.user_id)

    return router


async def _own(bus: CommandBus, tenant_id: str, user_id: str) -> OwnTenantResponse:
    own = next(own for own in await bus.query(ListOwnTenants(user_id)) if own.tenant.id == tenant_id)
    return OwnTenantResponse.of_own(own)


def admin_tenant_routes(bus: CommandBus) -> APIRouter:
    router = APIRouter(prefix='/admin/tenants', tags=['admin'])

    @router.get('')
    async def index(
        _admin: CurrentAdmin,
        q: Annotated[str, Query(max_length=200)] = '',
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> AdminTenantPageResponse:
        """All organizations, newest first; `q` searches the names."""
        return AdminTenantPageResponse.of(await bus.query(SearchTenants(query=q, offset=offset, limit=limit)))

    @router.patch('/{tenant_id}', dependencies=[audited('admin.tenant_status_changed')])
    async def change_status(
        tenant_id: Id, body: ChangeStatusRequest, request: Request, _admin: CurrentAdmin
    ) -> TenantResponse:
        note_audit(request, target=body.status)
        """Suspends an organization (nobody can use it, its data stays) or reactivates it."""
        return TenantResponse.of(await bus.execute(ChangeTenantStatus(tenant_id, body.status)))

    return router
