from collections.abc import Sequence

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

    async def viewers(self, tenant_id: str, queue_id: str, user_ids: Sequence[str]) -> set[str]:
        wanted = set(user_ids)
        if not wanted:
            return set()
        access = self._contracts.queue_access.get()
        found: set[str] = set()
        for member in await self._contracts.memberships.get().members(tenant_id):
            if member.user_id not in wanted:
                continue
            rights = await access.rights(
                tenant_id, member.user_id, queue_id, all_queues='queues.all' in member.permissions
            )
            if 'view' in rights:
                found.add(member.user_id)
        return found
