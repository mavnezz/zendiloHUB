from collections.abc import Sequence
from typing import Protocol

from zendilohub.core.domain.automation import AutomationChanges, TicketCriteria, TicketFacts

from ..models.rules import Rule, RuleKind


class RuleRepository(Protocol):
    async def of_tenant(self, tenant_id: str, kind: RuleKind) -> Sequence[Rule]:
        """In their order."""
        ...

    async def find(self, tenant_id: str, rule_id: str) -> Rule | None: ...

    async def active_schedules(self) -> Sequence[Rule]:
        """Of every organization."""
        ...

    async def save(self, rule: Rule) -> None: ...

    async def delete(self, tenant_id: str, rule_id: str) -> None: ...

    async def forget_tenant(self, tenant_id: str) -> None: ...


class Tickets(Protocol):
    """The tickets module (its `TicketAutomation` contract)."""

    async def facts(self, tenant_id: str, ticket_id: str) -> TicketFacts | None: ...

    async def find(self, tenant_id: str, criteria: TicketCriteria) -> list[str]: ...

    async def apply(self, tenant_id: str, ticket_id: str, changes: AutomationChanges, *, by: str) -> bool: ...

    async def excerpt(self, tenant_id: str, ticket_id: str) -> str:
        """The beginning of the newest message to or from the customer."""
        ...

    async def queue_name(self, tenant_id: str, queue_id: str) -> str | None: ...
