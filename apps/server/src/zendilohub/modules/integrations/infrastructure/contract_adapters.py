from zendilohub.core.contracts import Contracts
from zendilohub.core.domain.automation import TicketFacts


class ContractTickets:
    def __init__(self, contracts: Contracts) -> None:
        self._contracts = contracts

    async def facts(self, tenant_id: str, ticket_id: str) -> TicketFacts | None:
        return await self._contracts.ticket_automation.get().facts(tenant_id, ticket_id)
