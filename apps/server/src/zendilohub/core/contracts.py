"""
Synchronous contracts between modules: one module provides an implementation, another
module's infrastructure adapter calls it. (Asynchronous notifications are integration events.)
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from .domain.permissions import Permission
from .domain.queue_rights import QueueRight


class Slot[T]:
    """A late-bound implementation: the providing module may be built after the one that uses it."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._implementation: T | None = None

    def provide(self, implementation: T) -> None:
        if self._implementation is not None:
            raise RuntimeError(f'{self._name} is already provided')
        self._implementation = implementation

    def get(self) -> T:
        if self._implementation is None:
            raise RuntimeError(f'No module provides {self._name}')
        return self._implementation


class Invitations(Protocol):
    """Provided by tenancy, used by identity: on a self-hosted instance only invited people may sign up."""

    async def pending_for(self, email: str) -> bool:
        """Whether an organization invited the address and the invitation has not expired."""
        ...


@dataclass(frozen=True, kw_only=True)
class MemberCard:
    """A member of an organization as other modules see them."""

    user_id: str
    email: str
    permissions: frozenset[Permission]


class Memberships(Protocol):
    """Provided by tenancy, used by access (only members can be in groups) and tickets (who may get tickets)."""

    async def is_member(self, tenant_id: str, user_id: str) -> bool: ...

    async def members(self, tenant_id: str) -> list[MemberCard]:
        """Every member with what their role allows, oldest first."""
        ...


class QueueAccess(Protocol):
    """
    Provided by access, used by every module that shows or changes what lies in queues (tickets from phase 2):
    what a person may do in which queue, as the union of their groups' rights. `all_queues` (the permission
    `queues.all`) gives every right in every queue.
    """

    async def rights(
        self, tenant_id: str, user_id: str, queue_id: str, *, all_queues: bool = False
    ) -> frozenset[QueueRight]:
        """Empty if the queue does not exist or the person may do nothing in it."""
        ...

    async def visible(
        self, tenant_id: str, user_id: str, *, all_queues: bool = False
    ) -> Mapping[str, frozenset[QueueRight]]:
        """The queues the person may at least `view`, by id, with their rights; for filtering lists in SQL."""
        ...

    async def people_with(self, tenant_id: str, queue_id: str, right: QueueRight) -> frozenset[str]:
        """Who has the right in the queue through a group (not counting `queues.all`)."""
        ...


@dataclass(frozen=True, kw_only=True)
class ContactCard:
    """What other modules show of a customer: a contact with their company."""

    id: str
    name: str
    email: str | None
    phone: str | None
    company_id: str | None
    company_name: str | None


class Contacts(Protocol):
    """Provided by customers, used by tickets and channels: who wrote, and what to show of them."""

    async def identify(
        self, tenant_id: str, *, email: str | None, name: str = '', phone: str | None = None
    ) -> ContactCard:
        """The contact with this e-mail address (or phone number), made on first contact."""
        ...

    async def cards(self, tenant_id: str, contact_ids: list[str]) -> Mapping[str, ContactCard]:
        """By id; unknown ids are left out."""
        ...

    async def of_company(self, tenant_id: str, company_id: str) -> list[str]:
        """The ids of the company's contacts."""
        ...


class TicketUsage(Protocol):
    """Provided by tickets, used by access and customers: what still has tickets cannot simply be deleted."""

    async def in_queue(self, tenant_id: str, queue_id: str) -> int: ...

    async def of_customer(self, tenant_id: str, contact_id: str) -> int: ...


@dataclass(frozen=True)
class Contracts:
    """The slots modules provide for each other; added as modules need them."""

    invitations: Slot[Invitations] = field(default_factory=lambda: Slot('Invitations'))
    memberships: Slot[Memberships] = field(default_factory=lambda: Slot('Memberships'))
    queue_access: Slot[QueueAccess] = field(default_factory=lambda: Slot('QueueAccess'))
    contacts: Slot[Contacts] = field(default_factory=lambda: Slot('Contacts'))
    ticket_usage: Slot[TicketUsage] = field(default_factory=lambda: Slot('TicketUsage'))

    @classmethod
    def empty(cls) -> Contracts:
        return cls()
