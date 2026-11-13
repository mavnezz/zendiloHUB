from zendilohub.core.contracts import Contracts
from zendilohub.core.domain.automation import TicketFacts


class ContractDirectory:
    def __init__(self, contracts: Contracts) -> None:
        self._contracts = contracts

    async def facts(self, tenant_id: str, ticket_id: str) -> TicketFacts | None:
        return await self._contracts.ticket_automation.get().facts(tenant_id, ticket_id)

    async def email_of(self, tenant_id: str, user_id: str) -> str | None:
        for member in await self._contracts.memberships.get().members(tenant_id):
            if member.user_id == user_id:
                return member.email
        return None
