from zendilohub.core.contracts import Contracts
from zendilohub.core.domain.automation import AutomationChanges, TicketCriteria, TicketFacts


class ContractTickets:
    """`Tickets` through the tickets module's `TicketAutomation` contract."""

    def __init__(self, contracts: Contracts) -> None:
        self._contracts = contracts

    async def facts(self, tenant_id: str, ticket_id: str) -> TicketFacts | None:
        return await self._contracts.ticket_automation.get().facts(tenant_id, ticket_id)

    async def find(self, tenant_id: str, criteria: TicketCriteria) -> list[str]:
        return await self._contracts.ticket_automation.get().find(tenant_id, criteria)

    async def apply(self, tenant_id: str, ticket_id: str, changes: AutomationChanges, *, by: str) -> bool:
        return await self._contracts.ticket_automation.get().apply(tenant_id, ticket_id, changes, by=by)

    async def excerpt(self, tenant_id: str, ticket_id: str) -> str:
        return await self._contracts.ticket_automation.get().excerpt(tenant_id, ticket_id)

    async def queue_name(self, tenant_id: str, queue_id: str) -> str | None:
        return await self._contracts.queue_names.get().name_of(tenant_id, queue_id)
