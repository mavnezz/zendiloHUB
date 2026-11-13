from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from zendilohub.core.bus.message import Query
from zendilohub.core.domain.queue_rights import QUEUE_RIGHTS, QueueRight

from ...domain.models.grant import Grant
from ...domain.models.group import Group
from ...domain.models.queue import Queue
from ...domain.ports.repositories import GrantRepository, GroupRepository, QueueRepository

ALL_RIGHTS: frozenset[QueueRight] = frozenset(QUEUE_RIGHTS)


@dataclass(frozen=True)
class QueueWithRights:
    queue: Queue
    rights: frozenset[QueueRight]
    """What the person asking may do in it."""


@dataclass(frozen=True, kw_only=True)
class ListQueues(Query[Sequence[QueueWithRights]]):
    """
    The queues a person may see, with their rights there. `all_queues` (`queues.all`) sees every queue with every
    right; `managing` (`queues.manage`) lists every queue too, but with only the rights the person's groups give.
    """

    tenant_id: str
    user_id: str
    all_queues: bool = False
    managing: bool = False


class ListQueuesHandler:
    def __init__(self, queues: QueueRepository, grants: GrantRepository) -> None:
        self._queues = queues
        self._grants = grants

    async def handle(self, query: ListQueues) -> Sequence[QueueWithRights]:
        queues = await self._queues.of_tenant(query.tenant_id)
        if query.all_queues:
            return [QueueWithRights(queue, ALL_RIGHTS) for queue in queues]
        rights = await self._grants.of_user(query.tenant_id, query.user_id)
        return [
            QueueWithRights(queue, rights.get(queue.id, frozenset()))
            for queue in queues
            if query.managing or 'view' in rights.get(queue.id, frozenset())
        ]


@dataclass(frozen=True)
class ListGroups(Query[Sequence[Group]]):
    tenant_id: str


class ListGroupsHandler:
    def __init__(self, groups: GroupRepository) -> None:
        self._groups = groups

    async def handle(self, query: ListGroups) -> Sequence[Group]:
        return await self._groups.of_tenant(query.tenant_id)


@dataclass(frozen=True)
class ListGrants(Query[Sequence[Grant]]):
    """The rights matrix: every group's rights in every queue it has any in."""

    tenant_id: str


class ListGrantsHandler:
    def __init__(self, grants: GrantRepository) -> None:
        self._grants = grants

    async def handle(self, query: ListGrants) -> Sequence[Grant]:
        return await self._grants.of_tenant(query.tenant_id)


@dataclass(frozen=True, kw_only=True)
class RightsOf(Query[Mapping[str, frozenset[QueueRight]]]):
    """What a person may do, by queue id; the `QueueAccess` contract answers with it."""

    tenant_id: str
    user_id: str
    all_queues: bool = False


class RightsOfHandler:
    def __init__(self, queues: QueueRepository, grants: GrantRepository) -> None:
        self._queues = queues
        self._grants = grants

    async def handle(self, query: RightsOf) -> Mapping[str, frozenset[QueueRight]]:
        if query.all_queues:
            return {queue.id: ALL_RIGHTS for queue in await self._queues.of_tenant(query.tenant_id)}
        return await self._grants.of_user(query.tenant_id, query.user_id)
