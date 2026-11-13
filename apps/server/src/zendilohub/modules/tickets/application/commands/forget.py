from dataclasses import dataclass

from zendilohub.core.bus.message import Command
from zendilohub.core.domain.transaction import TransactionManager

from ...domain.models.actor import SYSTEM
from ...domain.ports.repositories import TicketRepository, WatcherRepository
from ..services.desk import Desk


@dataclass(frozen=True)
class ForgetMember(Command[None]):
    """Someone left the organization (tenant_id) or deleted their account (None): their tickets go back to nobody."""

    tenant_id: str | None
    user_id: str


class ForgetMemberHandler:
    def __init__(self, tickets: TicketRepository, watchers: WatcherRepository, desk: Desk) -> None:
        self._tickets = tickets
        self._watchers = watchers
        self._desk = desk

    async def handle(self, command: ForgetMember) -> None:
        await self._tickets.unassign(command.tenant_id, command.user_id, self._desk.clock.now())
        await self._watchers.forget(command.tenant_id, command.user_id)


@dataclass(frozen=True)
class ForgetTenant(Command[None]):
    tenant_id: str


class ForgetTenantHandler:
    def __init__(self, tickets: TicketRepository) -> None:
        self._tickets = tickets

    async def handle(self, command: ForgetTenant) -> None:
        await self._tickets.forget_tenant(command.tenant_id)


@dataclass(frozen=True)
class CloseDueTickets(Command[int]):
    """Closes `pending_close` tickets whose date has come (a scheduled job); returns how many."""

    limit: int = 500


class CloseDueTicketsHandler:
    def __init__(self, desk: Desk, transactions: TransactionManager) -> None:
        self._desk = desk
        self._transactions = transactions

    async def handle(self, command: CloseDueTickets) -> int:
        desk = self._desk
        due = await desk.tickets.due_to_close(desk.clock.now(), command.limit)
        for ticket in due:
            async with self._transactions.transaction():
                ticket.set_state('closed', desk.clock.now())
                await desk.save(ticket, SYSTEM)
        return len(due)
