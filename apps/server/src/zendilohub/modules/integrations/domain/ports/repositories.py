from collections.abc import Sequence
from typing import Protocol

from zendilohub.core.domain.automation import TicketFacts

from ..models.webhook import Delivery, Webhook


class WebhookRepository(Protocol):
    async def of_tenant(self, tenant_id: str) -> Sequence[Webhook]: ...

    async def find(self, tenant_id: str, webhook_id: str) -> Webhook | None: ...

    async def save(self, webhook: Webhook) -> None: ...

    async def secret(self, webhook_id: str) -> bytes | None: ...

    async def set_secret(self, webhook_id: str, sealed: bytes) -> None: ...

    async def delete(self, tenant_id: str, webhook_id: str) -> None: ...

    async def add_delivery(self, delivery: Delivery) -> None:
        """Keeps the last 50 per webhook."""
        ...

    async def deliveries(self, tenant_id: str, webhook_id: str) -> Sequence[Delivery]:
        """Newest first."""
        ...

    async def forget_tenant(self, tenant_id: str) -> None: ...


class Tickets(Protocol):
    async def facts(self, tenant_id: str, ticket_id: str) -> TicketFacts | None: ...
