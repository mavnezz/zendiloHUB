from collections.abc import Mapping, Sequence

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.contracts import Contracts
from zendilohub.core.domain.automation import AutomationChanges, TicketCriteria, TicketFacts
from zendilohub.core.domain.files import FileData
from zendilohub.core.domain.inbox import InboundEmail, OutgoingEmail, ReceivedTicket
from zendilohub.core.domain.portal import PortalThread, PortalTicket
from zendilohub.core.domain.queue_rights import QueueRight

from ..application.commands.automation import ApplyAutomation, ExcerptOf, FactsOf, FindTickets
from ..application.commands.email import MarkSent, OutgoingOf, ReceiveEmail, ThreadEmail
from ..application.commands.numbering import SubjectPrefix
from ..application.commands.portal import (
    PortalAttachment,
    PortalOpen,
    PortalReply,
    PortalThreadQuery,
    PortalTickets,
)
from ..application.queries.tickets import TicketUsageQuery
from ..domain.models.actor import Actor


class ContractQueueRights:
    """`QueueRights` through access's `QueueAccess` and tenancy's `Memberships` contracts."""

    def __init__(self, contracts: Contracts) -> None:
        self._contracts = contracts

    async def rights(self, tenant_id: str, actor: Actor, queue_id: str) -> frozenset[QueueRight]:
        if not actor.person and not actor.all_queues:
            return frozenset()
        access = self._contracts.queue_access.get()
        return await access.rights(tenant_id, actor.user_id, queue_id, all_queues=actor.all_queues)

    async def visible(self, tenant_id: str, actor: Actor) -> Mapping[str, frozenset[QueueRight]]:
        if not actor.person and not actor.all_queues:
            return {}
        return await self._contracts.queue_access.get().visible(tenant_id, actor.user_id, all_queues=actor.all_queues)

    async def assignees(self, tenant_id: str, queue_id: str) -> list[str]:
        access = self._contracts.queue_access.get()
        if not await access.rights(tenant_id, '', queue_id, all_queues=True):
            return []
        repliers = await access.people_with(tenant_id, queue_id, 'reply')
        return [
            member.user_id
            for member in await self._contracts.memberships.get().members(tenant_id)
            if member.user_id in repliers or 'queues.all' in member.permissions
        ]

    async def is_member(self, tenant_id: str, user_id: str) -> bool:
        return await self._contracts.memberships.get().is_member(tenant_id, user_id)


class ContractOrganizationTime:
    """`OrganizationTime` through tenancy's `OrganizationNames` contract."""

    def __init__(self, contracts: Contracts) -> None:
        self._contracts = contracts

    async def timezone_of(self, tenant_id: str) -> str | None:
        return await self._contracts.organizations.get().timezone_of(tenant_id)


class ContractCustomers:
    """`CustomerDirectory` through the customers module's `Contacts` contract."""

    def __init__(self, contracts: Contracts) -> None:
        self._contracts = contracts

    async def identify(self, tenant_id: str, *, email: str | None, name: str, phone: str | None) -> str:
        card = await self._contracts.contacts.get().identify(tenant_id, email=email, name=name, phone=phone)
        return card.id

    async def exists(self, tenant_id: str, contact_id: str) -> bool:
        return contact_id in await self._contracts.contacts.get().cards(tenant_id, [contact_id])

    async def of_company(self, tenant_id: str, company_id: str) -> list[str]:
        return await self._contracts.contacts.get().of_company(tenant_id, company_id)

    async def address_of(self, tenant_id: str, contact_id: str | None) -> tuple[str | None, str]:
        if contact_id is None:
            return None, ''
        card = (await self._contracts.contacts.get().cards(tenant_id, [contact_id])).get(contact_id)
        return (card.email, card.name) if card else (None, '')


class BusTicketUsage:
    """Tickets' side of the `TicketUsage` contract."""

    def __init__(self, bus: CommandBus) -> None:
        self._bus = bus

    async def in_queue(self, tenant_id: str, queue_id: str) -> int:
        return await self._bus.query(TicketUsageQuery(tenant_id=tenant_id, queue_id=queue_id))

    async def of_customer(self, tenant_id: str, contact_id: str) -> int:
        return await self._bus.query(TicketUsageQuery(tenant_id=tenant_id, contact_id=contact_id))


class BusTicketInbox:
    """Tickets' side of the `TicketInbox` contract."""

    def __init__(self, bus: CommandBus) -> None:
        self._bus = bus

    async def thread(self, tenant_id: str, email_ids: list[str], number: int | None) -> str | None:
        return await self._bus.query(ThreadEmail(tenant_id=tenant_id, email_ids=tuple(email_ids), number=number))

    async def receive(self, email: InboundEmail) -> ReceivedTicket:
        return await self._bus.execute(ReceiveEmail(email))

    async def outgoing(self, tenant_id: str, message_id: str) -> OutgoingEmail | None:
        return await self._bus.query(OutgoingOf(tenant_id=tenant_id, message_id=message_id))

    async def mark_sent(
        self, tenant_id: str, message_id: str, *, email_message_id: str, from_address: str, to: tuple[str, ...]
    ) -> None:
        await self._bus.execute(
            MarkSent(
                tenant_id=tenant_id,
                message_id=message_id,
                email_message_id=email_message_id,
                from_address=from_address,
                to=to,
            )
        )

    async def subject_prefix(self, tenant_id: str) -> str:
        return await self._bus.query(SubjectPrefix(tenant_id))


class BusTicketAutomation:
    """Tickets' side of the `TicketAutomation` contract."""

    def __init__(self, bus: CommandBus) -> None:
        self._bus = bus

    async def facts(self, tenant_id: str, ticket_id: str) -> TicketFacts | None:
        return await self._bus.query(FactsOf(tenant_id=tenant_id, ticket_id=ticket_id))

    async def find(self, tenant_id: str, criteria: TicketCriteria) -> list[str]:
        return await self._bus.query(FindTickets(tenant_id=tenant_id, criteria=criteria))

    async def apply(self, tenant_id: str, ticket_id: str, changes: AutomationChanges, *, by: str) -> bool:
        return await self._bus.execute(
            ApplyAutomation(tenant_id=tenant_id, ticket_id=ticket_id, changes=changes, by=by)
        )

    async def excerpt(self, tenant_id: str, ticket_id: str, *, limit: int = 500) -> str:
        return await self._bus.query(ExcerptOf(tenant_id=tenant_id, ticket_id=ticket_id, limit=limit))


class BusTicketPortal:
    """Tickets' side of the `TicketPortal` contract."""

    def __init__(self, bus: CommandBus) -> None:
        self._bus = bus

    async def tickets_of(self, tenant_id: str, contact_ids: list[str]) -> list[PortalTicket]:
        return await self._bus.query(PortalTickets(tenant_id=tenant_id, contact_ids=tuple(contact_ids)))

    async def thread(self, tenant_id: str, contact_ids: list[str], ticket_id: str) -> PortalThread | None:
        return await self._bus.query(
            PortalThreadQuery(tenant_id=tenant_id, contact_ids=tuple(contact_ids), ticket_id=ticket_id)
        )

    async def reply(
        self,
        tenant_id: str,
        contact_id: str,
        contact_ids: list[str],
        ticket_id: str,
        body: str,
        files: Sequence[FileData] = (),
    ) -> bool:
        return await self._bus.execute(
            PortalReply(
                tenant_id=tenant_id,
                contact_id=contact_id,
                contact_ids=tuple(contact_ids),
                ticket_id=ticket_id,
                body=body,
                files=tuple(files),
            )
        )

    async def open(
        self, tenant_id: str, contact_id: str, queue_id: str, subject: str, body: str, files: Sequence[FileData] = ()
    ) -> PortalTicket:
        return await self._bus.execute(
            PortalOpen(
                tenant_id=tenant_id,
                contact_id=contact_id,
                queue_id=queue_id,
                subject=subject,
                body=body,
                files=tuple(files),
            )
        )

    async def attachment(
        self, tenant_id: str, contact_ids: list[str], ticket_id: str, attachment_id: str
    ) -> FileData | None:
        return await self._bus.query(
            PortalAttachment(
                tenant_id=tenant_id, contact_ids=tuple(contact_ids), ticket_id=ticket_id, attachment_id=attachment_id
            )
        )
