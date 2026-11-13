from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from zendilohub.core.domain.automation import TicketFacts

from ..models.notification import Notification, Settings


class NotificationRepository(Protocol):
    async def add(self, notifications: Sequence[Notification]) -> None: ...

    async def of_user(self, tenant_id: str, user_id: str, *, unread: bool, limit: int) -> Sequence[Notification]:
        """Newest first."""
        ...

    async def unread(self, tenant_id: str, user_id: str) -> int: ...

    async def mark_read(self, tenant_id: str, user_id: str, ids: Sequence[str] | None, now: datetime) -> None:
        """None: all of them."""
        ...

    async def settings(self, tenant_id: str, user_id: str) -> Settings: ...

    async def save_settings(self, settings: Settings) -> None: ...

    async def forget(self, tenant_id: str | None, user_id: str) -> None: ...

    async def forget_tenant(self, tenant_id: str) -> None: ...


class Directory(Protocol):
    """Tickets and members as the notifications need them."""

    async def facts(self, tenant_id: str, ticket_id: str) -> TicketFacts | None: ...

    async def email_of(self, tenant_id: str, user_id: str) -> str | None: ...
