from zendilohub.core.contracts import Contracts
from zendilohub.core.domain.inbox import InboundEmail, OutgoingEmail, ReceivedTicket


class ContractTickets:
    """`Tickets` through the tickets module's `TicketInbox` contract."""

    def __init__(self, contracts: Contracts) -> None:
        self._contracts = contracts

    async def thread(self, tenant_id: str, email_ids: list[str], number: int | None) -> str | None:
        return await self._contracts.ticket_inbox.get().thread(tenant_id, email_ids, number)

    async def receive(self, email: InboundEmail) -> ReceivedTicket:
        return await self._contracts.ticket_inbox.get().receive(email)

    async def outgoing(self, tenant_id: str, message_id: str) -> OutgoingEmail | None:
        return await self._contracts.ticket_inbox.get().outgoing(tenant_id, message_id)

    async def mark_sent(
        self, tenant_id: str, message_id: str, *, email_message_id: str, from_address: str, to: tuple[str, ...]
    ) -> None:
        await self._contracts.ticket_inbox.get().mark_sent(
            tenant_id, message_id, email_message_id=email_message_id, from_address=from_address, to=to
        )


class ContractNames:
    """`Names` through tenancy's and access's contracts."""

    def __init__(self, contracts: Contracts) -> None:
        self._contracts = contracts

    async def organization(self, tenant_id: str) -> str:
        return await self._contracts.organizations.get().name_of(tenant_id) or ''

    async def queue(self, tenant_id: str, queue_id: str) -> str | None:
        return await self._contracts.queue_names.get().name_of(tenant_id, queue_id)

    async def member_email(self, tenant_id: str, user_id: str) -> str | None:
        for member in await self._contracts.memberships.get().members(tenant_id):
            if member.user_id == user_id:
                return member.email
        return None
