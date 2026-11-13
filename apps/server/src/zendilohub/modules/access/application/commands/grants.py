from collections.abc import Sequence
from dataclasses import dataclass

from zendilohub.core.bus.message import Command

from ...domain.exceptions import GroupNotFoundError, QueueNotFoundError
from ...domain.models.grant import Grant, checked_rights
from ...domain.ports.repositories import GrantRepository, GroupRepository, QueueRepository


@dataclass(frozen=True, kw_only=True)
class SetQueueRights(Command[Grant]):
    """What a group may do in a queue from now on; no rights take the grant away."""

    tenant_id: str
    group_id: str
    queue_id: str
    rights: Sequence[str]


class SetQueueRightsHandler:
    def __init__(self, queues: QueueRepository, groups: GroupRepository, grants: GrantRepository) -> None:
        self._queues = queues
        self._groups = groups
        self._grants = grants

    async def handle(self, command: SetQueueRights) -> Grant:
        rights = checked_rights(command.rights)
        if await self._queues.find(command.tenant_id, command.queue_id) is None:
            raise QueueNotFoundError()
        if await self._groups.find(command.tenant_id, command.group_id) is None:
            raise GroupNotFoundError()
        grant = Grant(group_id=command.group_id, queue_id=command.queue_id, rights=rights)
        await self._grants.set(command.tenant_id, grant)
        return grant
