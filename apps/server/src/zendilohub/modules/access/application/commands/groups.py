from collections.abc import Sequence
from dataclasses import dataclass, replace

from zendilohub.core.bus.message import Command
from zendilohub.core.domain.clock import Clock
from zendilohub.core.domain.id_generator import IdGenerator

from ...domain.exceptions import GroupLimitError, GroupNameTakenError, GroupNotFoundError, NotAMemberError
from ...domain.models.group import GROUPS_MAX, Group
from ...domain.ports.member_directory import MemberDirectory
from ...domain.ports.repositories import GroupRepository


@dataclass(frozen=True, kw_only=True)
class CreateGroup(Command[Group]):
    tenant_id: str
    name: str
    description: str = ''


class CreateGroupHandler:
    def __init__(self, groups: GroupRepository, ids: IdGenerator, clock: Clock) -> None:
        self._groups = groups
        self._ids = ids
        self._clock = clock

    async def handle(self, command: CreateGroup) -> Group:
        group = Group.create(
            id=self._ids.new_id(),
            tenant_id=command.tenant_id,
            name=command.name,
            description=command.description,
            now=self._clock.now(),
        )
        if await self._groups.count(command.tenant_id) >= GROUPS_MAX:
            raise GroupLimitError(GROUPS_MAX)
        if await self._groups.name_taken(command.tenant_id, group.name):
            raise GroupNameTakenError()
        await self._groups.save(group)
        return group


@dataclass(frozen=True, kw_only=True)
class UpdateGroup(Command[Group]):
    tenant_id: str
    group_id: str
    name: str
    description: str = ''


class UpdateGroupHandler:
    def __init__(self, groups: GroupRepository, clock: Clock) -> None:
        self._groups = groups
        self._clock = clock

    async def handle(self, command: UpdateGroup) -> Group:
        group = await _found(self._groups, command.tenant_id, command.group_id)
        group.change(name=command.name, description=command.description, now=self._clock.now())
        if await self._groups.name_taken(command.tenant_id, group.name, except_id=group.id):
            raise GroupNameTakenError()
        await self._groups.save(group)
        return group


@dataclass(frozen=True, kw_only=True)
class SetGroupMembers(Command[Group]):
    """Exactly these people are in the group afterwards; each must be a member of the organization."""

    tenant_id: str
    group_id: str
    user_ids: Sequence[str]


class SetGroupMembersHandler:
    def __init__(self, groups: GroupRepository, members: MemberDirectory, clock: Clock) -> None:
        self._groups = groups
        self._members = members
        self._clock = clock

    async def handle(self, command: SetGroupMembers) -> Group:
        group = await _found(self._groups, command.tenant_id, command.group_id)
        wanted = frozenset(command.user_ids)
        for user_id in sorted(wanted - group.member_ids):
            if not await self._members.is_member(command.tenant_id, user_id):
                raise NotAMemberError(user_id)
        changed = replace(group, member_ids=wanted, updated_at=self._clock.now())
        await self._groups.save(changed)
        return changed


@dataclass(frozen=True, kw_only=True)
class DeleteGroup(Command[Group]):
    """With its rights; its people keep what other groups give them."""

    tenant_id: str
    group_id: str


class DeleteGroupHandler:
    def __init__(self, groups: GroupRepository) -> None:
        self._groups = groups

    async def handle(self, command: DeleteGroup) -> Group:
        group = await _found(self._groups, command.tenant_id, command.group_id)
        await self._groups.delete(group.tenant_id, group.id)
        return group


async def _found(groups: GroupRepository, tenant_id: str, group_id: str) -> Group:
    group = await groups.find(tenant_id, group_id)
    if group is None:
        raise GroupNotFoundError()
    return group
