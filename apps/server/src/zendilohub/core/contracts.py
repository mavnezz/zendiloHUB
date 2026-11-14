"""
Synchronous contracts between modules: one module provides an implementation, another
module's infrastructure adapter calls it. (Asynchronous notifications are integration events.)
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from .domain.automation import AutomationChanges, TicketCriteria, TicketFacts
from .domain.contact_card import ContactCard as ContactCard
from .domain.files import FileData
from .domain.inbox import InboundEmail, OutgoingEmail, ReceivedTicket
from .domain.permissions import Permission
from .domain.portal import PortalThread, PortalTicket
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

    async def by_email(self, tenant_id: str, email: str) -> ContactCard | None:
        """The contact with this address, without making one."""
        ...


class TicketInbox(Protocol):
    """Provided by tickets, used by channels: e-mails become tickets and messages, replies go out as e-mails."""

    async def thread(self, tenant_id: str, email_ids: list[str], number: int | None) -> str | None:
        """The ticket an e-mail answers: by its `In-Reply-To`/`References`, else by the number in its subject."""
        ...

    async def receive(self, email: InboundEmail) -> ReceivedTicket: ...

    async def outgoing(self, tenant_id: str, message_id: str) -> OutgoingEmail | None:
        """None for messages that are no reply of the team."""
        ...

    async def mark_sent(
        self, tenant_id: str, message_id: str, *, email_message_id: str, from_address: str, to: tuple[str, ...]
    ) -> None:
        """Keeps the e-mail's id with the message, so the customer's answer finds the ticket."""
        ...


class TicketAutomation(Protocol):
    """Provided by tickets, used by automation, service and notifications: tickets as rules see and change them."""

    async def facts(self, tenant_id: str, ticket_id: str) -> TicketFacts | None: ...

    async def find(self, tenant_id: str, criteria: TicketCriteria) -> list[str]:
        """Ids of the open tickets that meet the criteria."""
        ...

    async def apply(self, tenant_id: str, ticket_id: str, changes: AutomationChanges, *, by: str) -> bool:
        """Changes the ticket as `by` (a rule's name), whatever anyone's rights; False if nothing changed."""
        ...


class TicketPortal(Protocol):
    """Provided by tickets, used by the portal: customers see and answer their own tickets."""

    async def tickets_of(self, tenant_id: str, contact_ids: list[str]) -> list[PortalTicket]:
        """Newest change first."""
        ...

    async def thread(self, tenant_id: str, contact_ids: list[str], ticket_id: str) -> PortalThread | None:
        """None if the ticket is none of these contacts'."""
        ...

    async def reply(
        self,
        tenant_id: str,
        contact_id: str,
        contact_ids: list[str],
        ticket_id: str,
        body: str,
        files: Sequence[FileData] = (),
    ) -> bool: ...

    async def open(
        self, tenant_id: str, contact_id: str, queue_id: str, subject: str, body: str, files: Sequence[FileData] = ()
    ) -> PortalTicket: ...

    async def attachment(
        self, tenant_id: str, contact_ids: list[str], ticket_id: str, attachment_id: str
    ) -> FileData | None:
        """A file of a public message of one of these contacts' tickets."""
        ...


class OrganizationNames(Protocol):
    """Provided by tenancy: an organization's name (for signatures and auto replies)."""

    async def name_of(self, tenant_id: str) -> str | None: ...


class QueueNames(Protocol):
    """Provided by access: a queue's name (for signatures and auto replies)."""

    async def name_of(self, tenant_id: str, queue_id: str) -> str | None: ...


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
    ticket_inbox: Slot[TicketInbox] = field(default_factory=lambda: Slot('TicketInbox'))
    ticket_automation: Slot[TicketAutomation] = field(default_factory=lambda: Slot('TicketAutomation'))
    ticket_portal: Slot[TicketPortal] = field(default_factory=lambda: Slot('TicketPortal'))
    organizations: Slot[OrganizationNames] = field(default_factory=lambda: Slot('OrganizationNames'))
    queue_names: Slot[QueueNames] = field(default_factory=lambda: Slot('QueueNames'))

    @classmethod
    def empty(cls) -> Contracts:
        return cls()
