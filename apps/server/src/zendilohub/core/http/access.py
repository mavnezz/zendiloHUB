"""
Who may call a route. Every API route declares one of the policies below (the kernel
refuses routes without one), so nothing becomes public by accident.

Routes of a tenant live below `/tenants/{tenant_id}/…` and use `CurrentMember` or `member_with(permission)`:
the tenant comes from the path, the role from the caller's membership, never from the request body. Besides logged-in
members, an organization's API keys (`Authorization: Bearer zhk_…`) reach its routes with the permissions they were
given; routes that only people may use (the team, the organization itself, the keys) say so with `people_only=True`
or `CurrentPerson`. AI assistants a member connected (Claude, ChatGPT) reach them like a key, only through the MCP
server's in-process calls: their access rides in the request's ASGI scope, which no request from outside can set.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any, Literal, Protocol, cast

from fastapi import Depends, Path, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.requests import HTTPConnection

from zendilohub.core.domain.app_domain_error import ForbiddenError, NotFoundError, UnauthenticatedError
from zendilohub.core.domain.assistant_access import AssistantAccess
from zendilohub.core.domain.permissions import Permission, TenantRole, permissions_of

from .ids import Id

if TYPE_CHECKING:
    from .http_kernel import HttpKernel

SESSION_COOKIE = 'zendilohub_session'
ASSISTANT_ACCESS = 'zendilohub.assistant_access'
"""The ASGI scope key of the MCP server's in-process calls for a connected AI assistant."""

type Role = Literal['user', 'admin']
"""A platform role: `admin` operates the platform (all tenants, plans), `user` is everyone else."""


@dataclass(frozen=True, kw_only=True)
class ApiKeyAccess:
    """What an API key may do: act in its organization with the permissions it was given."""

    key_id: str
    tenant_id: str
    permissions: frozenset[Permission]
    name: str


@dataclass(frozen=True, kw_only=True)
class Principal:
    """The logged-in user behind a request, or an organization's API key."""

    user_id: str
    """For an API key: the key's id."""
    email: str
    """For an API key: a label for the audit log (`API key: <name>`)."""
    role: Role
    session_id: str
    api_key: ApiKeyAccess | None = None

    @property
    def is_admin(self) -> bool:
        return self.role == 'admin' and self.api_key is None

    @classmethod
    def of_api_key(cls, access: ApiKeyAccess) -> Principal:
        return cls(user_id=access.key_id, email=f'API key: {access.name}', role='user', session_id='', api_key=access)

    @classmethod
    def of_assistant(cls, access: AssistantAccess) -> Principal:
        """The member who connected the assistant, held to what the connection may do like a key."""
        key = ApiKeyAccess(
            key_id=access.connection_id,
            tenant_id=access.tenant_id,
            permissions=access.permissions,
            name=access.client_name,
        )
        return cls(
            user_id=access.user_id,
            email=f'{access.client_name} ({access.email})',
            role='user',
            session_id='',
            api_key=key,
        )


@dataclass(frozen=True, kw_only=True)
class Member:
    """The logged-in user acting inside one tenant with their role there, or one of the tenant's API keys."""

    principal: Principal
    tenant_id: str
    role: TenantRole | None
    """None for an API key: it has permissions of its own, no role."""
    permissions: frozenset[Permission]

    @classmethod
    def person(cls, principal: Principal, tenant_id: str, role: TenantRole) -> Member:
        return cls(principal=principal, tenant_id=tenant_id, role=role, permissions=frozenset(permissions_of(role)))

    @classmethod
    def key(cls, principal: Principal, access: ApiKeyAccess) -> Member:
        return cls(principal=principal, tenant_id=access.tenant_id, role=None, permissions=access.permissions)

    @property
    def user_id(self) -> str:
        return self.principal.user_id

    @property
    def person_role(self) -> TenantRole:
        """The role of a member who logged in, for the routes only people may use."""
        if self.role is None:
            raise PeopleOnlyError()
        return self.role

    def can(self, permission: Permission) -> bool:
        return permission in self.permissions

    @property
    def via_api_key(self) -> bool:
        return self.principal.api_key is not None

    def require(self, permission: Permission) -> None:
        if not self.can(permission):
            raise PermissionDeniedError(permission)


class AuthGuard(Protocol):
    """Implemented by the module that owns accounts."""

    async def authenticate(self, session_token: str) -> Principal | None: ...


class ApiKeyGuard(Protocol):
    """Implemented by the module that owns the organizations' API keys."""

    async def authenticate_key(self, token: str) -> ApiKeyAccess | None:
        """None for unknown keys and keys of organizations that are not active."""
        ...


class MembershipGuard(Protocol):
    """Implemented by the module that owns tenants."""

    async def role_in(self, tenant_id: str, user_id: str) -> TenantRole | None:
        """The user's role in an active tenant, or None if they are no member (or the tenant does not exist)."""
        ...


class LoginRequiredError(UnauthenticatedError):
    def __init__(self) -> None:
        super().__init__('unauthenticated', 'Login required')


class AdminRequiredError(ForbiddenError):
    def __init__(self) -> None:
        super().__init__('forbidden', 'Only administrators may do this')


class TenantNotFoundError(NotFoundError):
    """Also for tenants the caller is no member of: their existence is none of the caller's business."""

    def __init__(self) -> None:
        super().__init__('tenant_not_found', 'The organization does not exist')


class PeopleOnlyError(ForbiddenError):
    def __init__(self) -> None:
        super().__init__('people_only', 'API keys cannot do this; a member has to log in')


class PermissionDeniedError(ForbiddenError):
    def __init__(self, permission: Permission) -> None:
        super().__init__('permission_denied', 'You may not do this', {'permission': permission})


_UNRESOLVED = object()


async def resolve_principal(request: HTTPConnection) -> Principal | None:
    """The request's (or WebSocket's) principal, looked up once per request."""
    cached = getattr(request.state, 'principal', _UNRESOLVED)
    if cached is not _UNRESOLVED:
        return cast(Principal | None, cached)
    kernel: HttpKernel = request.app.state.kernel
    token = request.cookies.get(SESSION_COOKIE)
    principal = await kernel.authenticate(token) if token else None
    request.state.principal = principal
    return principal


def public() -> None:
    """Policy: reachable by anyone."""


async def optional_user(request: Request) -> Principal | None:
    """Policy: reachable by anyone; logged-in users are recognized."""
    return await resolve_principal(request)


async def require_user(request: Request) -> Principal:
    """Policy: logged-in users only."""
    principal = await resolve_principal(request)
    if principal is None:
        raise LoginRequiredError()
    return principal


async def require_admin(principal: Annotated[Principal, Depends(require_user)]) -> Principal:
    """Policy: platform administrators only."""
    if not principal.is_admin:
        raise AdminRequiredError()
    return principal


bearer = HTTPBearer(
    auto_error=False,
    scheme_name='API key',
    description='An API key of the organization (`zhk_…`); it acts with its permissions in that organization only.',
)


async def require_caller(
    request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
) -> Principal:
    """A logged-in user (session cookie) or, without one, a connected AI assistant or an API key."""
    principal = await resolve_principal(request)
    assistant = request.scope.get(ASSISTANT_ACCESS)
    if principal is None and isinstance(assistant, AssistantAccess):
        principal = Principal.of_assistant(assistant)
        request.state.principal = principal
    elif principal is None and credentials is not None:
        kernel: HttpKernel = request.app.state.kernel
        access = await kernel.authenticate_key(credentials.credentials)
        principal = Principal.of_api_key(access) if access else None
        request.state.principal = principal
    if principal is None:
        raise LoginRequiredError()
    return principal


async def require_member(
    request: Request,
    principal: Annotated[Principal, Depends(require_caller)],
    tenant_id: Annotated[Id, Path()],
) -> Member:
    """Policy: members of the tenant in the path only (or its API keys)."""
    if principal.api_key is not None:
        if principal.api_key.tenant_id != tenant_id:
            raise TenantNotFoundError()
        return Member.key(principal, principal.api_key)
    kernel: HttpKernel = request.app.state.kernel
    role = await kernel.role_in(tenant_id, principal.user_id)
    if role is None:
        raise TenantNotFoundError()
    return Member.person(principal, tenant_id, role)


async def require_person(member: Annotated[Member, Depends(require_member)]) -> Member:
    """Policy: members of the tenant in the path who logged in (no API keys)."""
    if member.via_api_key:
        raise PeopleOnlyError()
    return member


async def socket_member(connection: HTTPConnection, tenant_id: str) -> Member | None:
    """
    For WebSocket routes, which cannot use the policies above: the logged-in member of the tenant, or None.
    The cross-site guard has checked the origin of the handshake already.
    """
    principal = await resolve_principal(connection)
    if principal is None:
        return None
    kernel: HttpKernel = connection.app.state.kernel
    role = await kernel.role_in(tenant_id, principal.user_id)
    return Member.person(principal, tenant_id, role) if role else None


def member_with(permission: Permission, *, people_only: bool = False) -> Any:
    """Policy: members of the tenant in the path whose role allows it (or its API keys with that permission)."""

    async def dependency(
        member: Annotated[Member, Depends(require_person if people_only else require_member)],
    ) -> Member:
        member.require(permission)
        return member

    return Depends(dependency)


ACCESS_POLICIES: tuple[Callable[..., Awaitable[object] | None], ...] = (
    public,
    optional_user,
    require_user,
    require_admin,
    require_member,
    require_person,
)

Public = Depends(public)
OptionalUser = Annotated[Principal | None, Depends(optional_user)]
CurrentUser = Annotated[Principal, Depends(require_user)]
CurrentAdmin = Annotated[Principal, Depends(require_admin)]
CurrentMember = Annotated[Member, Depends(require_member)]
CurrentPerson = Annotated[Member, Depends(require_person)]
