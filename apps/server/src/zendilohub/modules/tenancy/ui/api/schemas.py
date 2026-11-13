from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from zendilohub.core.domain.permissions import (
    BUILTIN_ROLES,
    OWNER_ONLY,
    PERMISSIONS,
    BuiltinRole,
    Permission,
    ordered,
    permissions_of,
)
from zendilohub.core.http.access import Member

from ...application.commands.api_keys import CreatedApiKey
from ...application.commands.roles import RoleOverview
from ...application.queries.members import InvitationPreview
from ...domain.models.api_key import KEY_PERMISSIONS, NAME_MAX, ApiKey, KeyPermission
from ...domain.models.invitation import Invitation
from ...domain.models.membership import Membership
from ...domain.models.role import DESCRIPTION_MAX, CustomRole
from ...domain.models.role import NAME_MAX as ROLE_NAME_MAX
from ...domain.models.tenant import Tenant
from ...domain.ports.repositories import OwnTenant, TenantPage

type LocaleValue = Literal['de', 'en']
type RoleValue = str
"""A built-in role (`owner`, `admin`, `manager`, `agent`) or the id of one of the organization's own roles."""
type StatusValue = Literal['active', 'suspended']


class Request(BaseModel):
    model_config = ConfigDict(extra='forbid')


class CreateTenantRequest(Request):
    name: str = Field(max_length=200)
    timezone: str = Field(default='Europe/Berlin', max_length=64)
    locale: LocaleValue = 'de'


class UpdateTenantRequest(Request):
    name: str | None = Field(default=None, max_length=200)
    timezone: str | None = Field(default=None, max_length=64)
    locale: LocaleValue | None = None


class ChangeStatusRequest(Request):
    status: StatusValue


class ChangeRoleRequest(Request):
    role: RoleValue = Field(min_length=1, max_length=64)


class InviteRequest(Request):
    email: str = Field(max_length=254)
    role: RoleValue = Field(default='agent', min_length=1, max_length=64)


class RoleRequest(Request):
    name: str = Field(max_length=ROLE_NAME_MAX)
    description: str = Field(default='', max_length=DESCRIPTION_MAX)
    permissions: list[Permission] = Field(min_length=1, max_length=len(PERMISSIONS))


class TokenRequest(Request):
    token: str = Field(max_length=256)


class TenantResponse(BaseModel):
    id: str
    name: str
    status: StatusValue
    timezone: str
    locale: LocaleValue
    created_at: datetime

    @classmethod
    def of(cls, tenant: Tenant) -> TenantResponse:
        return cls(
            id=tenant.id,
            name=tenant.name,
            status=tenant.status,
            timezone=tenant.timezone,
            locale=tenant.locale,
            created_at=tenant.created_at,
        )


class OwnTenantResponse(TenantResponse):
    """A tenant as the caller sees it: with their role and what it allows."""

    role: RoleValue | None
    """None for an API key: it has the permissions it was given, no role."""
    role_name: str | None = None
    """The name of an own role; built-in roles are translated by the web app."""
    permissions: list[Permission]

    @classmethod
    def of_role(
        cls, tenant: Tenant, role: RoleValue, permissions: frozenset[Permission], role_name: str | None = None
    ) -> OwnTenantResponse:
        return cls(
            **TenantResponse.of(tenant).model_dump(),
            role=role,
            role_name=role_name,
            permissions=ordered(permissions),
        )

    @classmethod
    def of_member(cls, tenant: Tenant, member: Member) -> OwnTenantResponse:
        permissions = [permission for permission in PERMISSIONS if member.can(permission)]
        return cls(**TenantResponse.of(tenant).model_dump(), role=member.role, permissions=permissions)

    @classmethod
    def of_own(cls, own: OwnTenant) -> OwnTenantResponse:
        return cls.of_role(own.tenant, own.membership.role, own.membership.permissions, own.membership.role_name)


class MemberResponse(BaseModel):
    user_id: str
    email: str
    role: RoleValue
    joined_at: datetime

    @classmethod
    def of(cls, member: Membership) -> MemberResponse:
        return cls(user_id=member.user_id, email=member.email, role=member.role, joined_at=member.created_at)


class InvitationResponse(BaseModel):
    id: str
    email: str
    role: RoleValue
    created_at: datetime
    expires_at: datetime

    @classmethod
    def of(cls, invitation: Invitation) -> InvitationResponse:
        return cls(
            id=invitation.id,
            email=invitation.email,
            role=invitation.role,
            created_at=invitation.created_at,
            expires_at=invitation.expires_at,
        )


class InvitationPreviewResponse(BaseModel):
    tenant_name: str
    email: str
    role: RoleValue
    role_name: str | None
    """The name of an own role; built-in roles are translated by the web app."""
    expires_at: datetime

    @classmethod
    def of(cls, preview: InvitationPreview) -> InvitationPreviewResponse:
        return cls(
            tenant_name=preview.tenant.name,
            email=preview.invitation.email,
            role=preview.invitation.role,
            role_name=preview.role_name,
            expires_at=preview.invitation.expires_at,
        )


class AdminTenantResponse(TenantResponse):
    member_count: int


class AdminTenantPageResponse(BaseModel):
    items: list[AdminTenantResponse]
    total: int

    @classmethod
    def of(cls, page: TenantPage) -> AdminTenantPageResponse:
        return cls(
            items=[
                AdminTenantResponse(**TenantResponse.of(item.tenant).model_dump(), member_count=item.member_count)
                for item in page.items
            ],
            total=page.total,
        )


class RoleResponse(BaseModel):
    """A built-in role (`id` is its key, `name` null: the web app translates it) or one of the organization's own."""

    id: str
    name: str | None
    description: str
    builtin: bool
    permissions: list[Permission]
    member_count: int

    @classmethod
    def of_builtin(cls, role: BuiltinRole, members: int) -> RoleResponse:
        return cls(
            id=role, name=None, description='', builtin=True, permissions=permissions_of(role), member_count=members
        )

    @classmethod
    def of(cls, role: CustomRole, members: int) -> RoleResponse:
        return cls(
            id=role.id,
            name=role.name,
            description=role.description,
            builtin=False,
            permissions=ordered(role.permissions),
            member_count=members,
        )


class RolesResponse(BaseModel):
    """Every role of the organization, built-in first, and which permissions exist."""

    permissions: list[Permission]
    owner_only: list[Permission]
    """What no own role may hold."""
    roles: list[RoleResponse]

    @classmethod
    def of(cls, overview: RoleOverview) -> RolesResponse:
        count = overview.members
        return cls(
            permissions=list(PERMISSIONS),
            owner_only=ordered(OWNER_ONLY),
            roles=[RoleResponse.of_builtin(role, count.get(role, 0)) for role in BUILTIN_ROLES]
            + [RoleResponse.of(role, count.get(role.id, 0)) for role in overview.roles],
        )


class ApiKeyRequest(Request):
    name: str = Field(max_length=NAME_MAX)
    permissions: list[KeyPermission] = Field(max_length=len(KEY_PERMISSIONS))
    """What the key may do, at least one permission (what needs a person or an owner is not among them)."""


class ApiKeyResponse(BaseModel):
    id: str
    name: str
    permissions: list[KeyPermission]
    start: str
    """The first characters of the key, to tell keys apart."""
    created_at: datetime
    last_used_at: datetime | None
    """Updated at most once a minute."""

    @classmethod
    def of(cls, key: ApiKey) -> ApiKeyResponse:
        return cls(
            id=key.id,
            name=key.name,
            permissions=list(key.permissions),
            start=key.start,
            created_at=key.created_at,
            last_used_at=key.last_used_at,
        )


class CreatedApiKeyResponse(BaseModel):
    api_key: ApiKeyResponse
    key: str
    """`zhk_…`: shown this once. Send it as `Authorization: Bearer <key>`."""

    @classmethod
    def of(cls, created: CreatedApiKey) -> CreatedApiKeyResponse:
        return cls(api_key=ApiKeyResponse.of(created.key), key=created.secret)
