from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Protocol

from zendilohub.core.domain.queue_rights import QueueRight

from ..models.actor import Actor
from ..models.assist import AssistInput


class QueueRights(Protocol):
    """What someone may do in which queue (the access module knows)."""

    async def rights(self, tenant_id: str, actor: Actor, queue_id: str) -> frozenset[QueueRight]: ...

    async def visible(self, tenant_id: str, actor: Actor) -> Mapping[str, frozenset[QueueRight]]: ...

    async def assignees(self, tenant_id: str, queue_id: str) -> list[str]:
        """The members who may reply in the queue, so tickets may go to them."""
        ...

    async def is_member(self, tenant_id: str, user_id: str) -> bool: ...


class CustomerDirectory(Protocol):
    """The customers module: who a ticket is about."""

    async def identify(self, tenant_id: str, *, email: str | None, name: str, phone: str | None) -> str:
        """The contact's id; made on first contact."""
        ...

    async def exists(self, tenant_id: str, contact_id: str) -> bool: ...

    async def of_company(self, tenant_id: str, company_id: str) -> list[str]: ...

    async def address_of(self, tenant_id: str, contact_id: str | None) -> tuple[str | None, str]:
        """The contact's e-mail address (None without one) and name."""
        ...


class Presence(Protocol):
    """Who has a ticket open right now (collision detection, like Zammad's)."""

    async def here(self, tenant_id: str, ticket_id: str, user_id: str, *, writing: bool) -> list[tuple[str, bool]]:
        """Marks the user as looking at the ticket (for half a minute); returns the others there, writing or not."""
        ...


class TicketWriter(Protocol):
    """A language model that summarizes tickets and drafts replies (optional: off without an API key)."""

    @property
    def enabled(self) -> bool: ...

    async def write(self, request: AssistInput) -> str:
        """The text; raises AssistantFailedError when the model does not answer usefully."""
        ...


class FileStore(Protocol):
    """Where the content of attachments lives (files on disk); keyed by organization and attachment id."""

    async def put(self, tenant_id: str, file_id: str, content: bytes) -> None: ...

    async def get(self, tenant_id: str, file_id: str) -> bytes | None: ...

    async def delete(self, tenant_id: str, file_id: str) -> None: ...

    def stored(self, older_than: datetime) -> Iterable[tuple[str, str]]:
        """(tenant, file) of the files last written before `older_than`."""
        ...


class OrganizationTime(Protocol):
    """The organization's time zone (tenancy knows it): date numbers start a new day at its midnight."""

    async def timezone_of(self, tenant_id: str) -> str | None: ...
