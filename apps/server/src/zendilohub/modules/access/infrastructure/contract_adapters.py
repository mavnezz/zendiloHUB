from collections.abc import Mapping

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.contracts import Contracts
from zendilohub.core.domain.queue_rights import QueueRight

from ..application.queries.access import PeopleWith, RightsOf


class TenancyMembers:
    """`MemberDirectory` through tenancy's `Memberships` contract."""

    def __init__(self, contracts: Contracts) -> None:
        self._contracts = contracts

    async def is_member(self, tenant_id: str, user_id: str) -> bool:
        return await self._contracts.memberships.get().is_member(tenant_id, user_id)


class QueueTickets:
    """`QueueUsage` through the tickets module's `TicketUsage` contract."""

    def __init__(self, contracts: Contracts) -> None:
        self._contracts = contracts

    async def in_queue(self, tenant_id: str, queue_id: str) -> int:
        return await self._contracts.ticket_usage.get().in_queue(tenant_id, queue_id)


class BusQueueAccess:
    """Access's side of the `QueueAccess` contract."""

    def __init__(self, bus: CommandBus) -> None:
        self._bus = bus

    async def rights(
        self, tenant_id: str, user_id: str, queue_id: str, *, all_queues: bool = False
    ) -> frozenset[QueueRight]:
        return (await self.visible(tenant_id, user_id, all_queues=all_queues)).get(queue_id, frozenset())

    async def visible(
        self, tenant_id: str, user_id: str, *, all_queues: bool = False
    ) -> Mapping[str, frozenset[QueueRight]]:
        rights = await self._bus.query(RightsOf(tenant_id=tenant_id, user_id=user_id, all_queues=all_queues))
        return {queue_id: each for queue_id, each in rights.items() if 'view' in each}

    async def people_with(self, tenant_id: str, queue_id: str, right: QueueRight) -> frozenset[str]:
        return await self._bus.query(PeopleWith(tenant_id=tenant_id, queue_id=queue_id, right=right))
