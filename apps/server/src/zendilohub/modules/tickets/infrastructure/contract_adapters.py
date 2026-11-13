from collections.abc import Mapping

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.contracts import Contracts
from zendilohub.core.domain.queue_rights import QueueRight

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


class BusTicketUsage:
    """Tickets' side of the `TicketUsage` contract."""

    def __init__(self, bus: CommandBus) -> None:
        self._bus = bus

    async def in_queue(self, tenant_id: str, queue_id: str) -> int:
        return await self._bus.query(TicketUsageQuery(tenant_id=tenant_id, queue_id=queue_id))

    async def of_customer(self, tenant_id: str, contact_id: str) -> int:
        return await self._bus.query(TicketUsageQuery(tenant_id=tenant_id, contact_id=contact_id))
