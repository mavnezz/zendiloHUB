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


@dataclass(frozen=True, kw_only=True)
class QueueDeleted(IntegrationEvent):
    """A queue is gone (with the rights on it); modules that keep things per queue clean up."""

    tenant_id: str
    queue_id: str


@dataclass(frozen=True, kw_only=True)
class TicketCreated(IntegrationEvent):
    tenant_id: str
    ticket_id: str
    number: int
    queue_id: str
    customer_id: str | None
    channel: str
    actor_id: str | None


@dataclass(frozen=True, kw_only=True)
class TicketChanged(IntegrationEvent):
    """Fields of a ticket changed: (field, old, new) as text, e.g. ('state', 'open', 'closed')."""

    tenant_id: str
    ticket_id: str
    actor_id: str | None
    changes: tuple[tuple[str, str | None, str | None], ...]
    automated: bool = False
    """Made by a trigger or scheduled job: triggers do not react to it (no loops)."""


@dataclass(frozen=True, kw_only=True)
class MessageAdded(IntegrationEvent):
    """
    A message joined a ticket. `public` + `out` is a reply the channels module sends to the customer; `in` came from
    the customer (by e-mail, or written down by an agent).
    """

    tenant_id: str
    ticket_id: str
    message_id: str
    kind: str
    direction: str
    author_id: str | None
    mentions: tuple[str, ...] = ()
    """Members mentioned in an internal note."""
    automated: bool = False
    first: bool = False
    """The message opened the ticket (`TicketCreated` came just before)."""


@dataclass(frozen=True, kw_only=True)
class SlaBreached(IntegrationEvent):
    """A ticket missed its first response or solution time."""

    tenant_id: str
    ticket_id: str
    kind: str
    """`first_response` or `solution`."""
