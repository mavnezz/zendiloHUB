from datetime import datetime
from typing import Literal, Protocol

from zendilohub.core.domain.contact_card import ContactCard
from zendilohub.core.domain.portal import PortalThread, PortalTicket

from ..models.portal import PortalLogin, PortalSettings

type LoginKind = Literal['link', 'session']


class PortalRepository(Protocol):
    async def settings(self, tenant_id: str) -> PortalSettings: ...

    async def save_settings(self, settings: PortalSettings) -> None: ...

    async def add_login(self, kind: LoginKind, login: PortalLogin) -> None: ...

    async def find_login(self, kind: LoginKind, token_hash: str, now: datetime) -> PortalLogin | None:
        """None if unknown or expired."""
        ...

    async def remove_login(self, kind: LoginKind, token_hash: str) -> None: ...

    async def remove_expired(self, now: datetime) -> None: ...

    async def forget_tenant(self, tenant_id: str) -> None: ...


class Customers(Protocol):
    async def by_email(self, tenant_id: str, email: str) -> ContactCard | None: ...

    async def card(self, tenant_id: str, contact_id: str) -> ContactCard | None: ...

    async def of_company(self, tenant_id: str, company_id: str) -> list[str]: ...


class Tickets(Protocol):
    async def tickets_of(self, tenant_id: str, contact_ids: list[str]) -> list[PortalTicket]: ...

    async def thread(self, tenant_id: str, contact_ids: list[str], ticket_id: str) -> PortalThread | None: ...

    async def reply(
        self, tenant_id: str, contact_id: str, contact_ids: list[str], ticket_id: str, body: str
    ) -> bool: ...

    async def open(self, tenant_id: str, contact_id: str, queue_id: str, subject: str, body: str) -> PortalTicket: ...
