from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from zendilohub.core.domain.permissions import PERMISSIONS, TENANT_ROLES, Permission, TenantRole, permissions_of
from zendilohub.core.http.access import Member

from ...application.commands.api_keys import CreatedApiKey
from ...application.queries.members import InvitationPreview
from ...domain.models.api_key import KEY_PERMISSIONS, NAME_MAX, ApiKey, KeyPermission
from ...domain.models.invitation import Invitation
from ...domain.models.membership import Membership
from ...domain.models.tenant import Tenant
from ...domain.ports.repositories import OwnTenant, TenantPage

type LocaleValue = Literal['de', 'en']
type RoleValue = Literal['owner', 'admin', 'manager', 'agent']
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
    role: RoleValue


class InviteRequest(Request):
    email: str = Field(max_length=254)
    role: RoleValue = 'agent'


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
    permissions: list[Permission]

    @classmethod
    def of_role(cls, tenant: Tenant, role: TenantRole) -> OwnTenantResponse:
        return cls(**TenantResponse.of(tenant).model_dump(), role=role, permissions=permissions_of(role))

    @classmethod
    def of_member(cls, tenant: Tenant, member: Member) -> OwnTenantResponse:
        permissions = [permission for permission in PERMISSIONS if member.can(permission)]
        return cls(**TenantResponse.of(tenant).model_dump(), role=member.role, permissions=permissions)

    @classmethod
    def of_own(cls, own: OwnTenant) -> OwnTenantResponse:
        return cls.of_role(own.tenant, own.membership.role)


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
    expires_at: datetime

    @classmethod
    def of(cls, preview: InvitationPreview) -> InvitationPreviewResponse:
        return cls(
            tenant_name=preview.tenant.name,
            email=preview.invitation.email,
            role=preview.invitation.role,
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


class RoleMatrixResponse(BaseModel):
    """Which role may do what; the web app shows it on the role permissions page."""

    roles: list[RoleValue]
    permissions: dict[Permission, list[RoleValue]]

    @classmethod
    def current(cls) -> RoleMatrixResponse:
        return cls(
            roles=list(TENANT_ROLES),
            permissions={
                permission: [role for role in TENANT_ROLES if role in roles]
                for permission, roles in PERMISSIONS.items()
            },
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
