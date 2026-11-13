from collections.abc import Mapping, Sequence
from typing import Protocol

from zendilohub.core.domain.queue_rights import QueueRight

from ..models.grant import Grant
from ..models.group import Group
from ..models.queue import Queue


class QueueRepository(Protocol):
    async def of_tenant(self, tenant_id: str) -> Sequence[Queue]:
        """By name."""
        ...

    async def find(self, tenant_id: str, queue_id: str) -> Queue | None: ...

    async def count(self, tenant_id: str) -> int: ...

    async def name_taken(self, tenant_id: str, name: str, *, except_id: str | None = None) -> bool:
        """Names are compared ignoring case."""
        ...

    async def save(self, queue: Queue) -> None: ...

    async def delete(self, tenant_id: str, queue_id: str) -> None:
        """With the rights on it."""
        ...


class GroupRepository(Protocol):
    async def of_tenant(self, tenant_id: str) -> Sequence[Group]:
        """By name, with their members."""
        ...

    async def find(self, tenant_id: str, group_id: str) -> Group | None: ...

    async def count(self, tenant_id: str) -> int: ...

    async def name_taken(self, tenant_id: str, name: str, *, except_id: str | None = None) -> bool: ...

    async def save(self, group: Group) -> None:
        """The group and exactly its `member_ids`."""
        ...

    async def delete(self, tenant_id: str, group_id: str) -> None: ...

    async def remove_member(self, tenant_id: str, user_id: str) -> None:
        """From every group of the organization."""
        ...

    async def remove_user(self, user_id: str) -> None:
        """From every group of every organization."""
        ...


class GrantRepository(Protocol):
    async def of_tenant(self, tenant_id: str) -> Sequence[Grant]: ...

    async def set(self, tenant_id: str, grant: Grant) -> None:
        """Replaces the group's rights in the queue; no rights delete the grant."""
        ...

    async def of_user(self, tenant_id: str, user_id: str) -> Mapping[str, frozenset[QueueRight]]:
        """The union of the rights of the person's groups, by queue id (queues without rights are left out)."""
        ...


class TenantData(Protocol):
    async def forget(self, tenant_id: str) -> None:
        """Every queue, group and grant of the organization."""
        ...
