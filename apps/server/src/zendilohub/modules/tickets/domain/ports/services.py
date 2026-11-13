from collections.abc import Mapping
from typing import Protocol

from zendilohub.core.domain.queue_rights import QueueRight

from ..models.actor import Actor


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
