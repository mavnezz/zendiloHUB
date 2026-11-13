"""
Events modules publish for each other. Modules never import each other;
they only share these contracts.
"""

from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class IntegrationEvent:
    """Base class of all integration events."""


@dataclass(frozen=True, kw_only=True)
class UserRegistered(IntegrationEvent):
    """A new account exists (not yet verified)."""

    user_id: str
    email: str


@dataclass(frozen=True, kw_only=True)
class UserDeleted(IntegrationEvent):
    """An account was deleted: every module deletes the user's data (GDPR)."""

    user_id: str
    email: str


@dataclass(frozen=True, kw_only=True)
class TenantCreated(IntegrationEvent):
    """A new organization exists; `owner_id` created it."""

    tenant_id: str
    owner_id: str


@dataclass(frozen=True, kw_only=True)
class MemberRemoved(IntegrationEvent):
    """Someone left an organization or was removed from it; links to them (e.g. their test phone) go."""

    tenant_id: str
    user_id: str


@dataclass(frozen=True, kw_only=True)
class TenantDeleted(IntegrationEvent):
    """An organization is being deleted: every module deletes the tenant's data (in the same transaction)."""

    tenant_id: str


@dataclass(frozen=True, kw_only=True)
class ActionPerformed(IntegrationEvent):
    """Someone changed something through the API (or tried to); the audit log records it."""

    action: str
    """Stable name, e.g. `member.role_changed`."""
    tenant_id: str | None
    """None for actions outside an organization (login, platform administration)."""
    target: str | None
    actor_id: str | None
    actor_email: str | None
    succeeded: bool
    status: int
    """The HTTP status of the answer."""
    client: str | None
    """The client's IP address (behind trusted proxies: the forwarded one)."""


@dataclass(frozen=True, kw_only=True)
class InstanceSetUp(IntegrationEvent):
    """The setup wizard of a self-hosted instance made its first administrator; tenancy makes the organization."""

    user_id: str
    email: str
    organization_name: str
    timezone: str
    locale: str
