from typing import Annotated

from fastapi import APIRouter, Request, Response

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.domain.queue_rights import PRESETS
from zendilohub.core.http.access import CurrentMember, Member, member_with
from zendilohub.core.http.audit import audited, note_audit
from zendilohub.core.http.ids import Id

from ...application.commands.grants import SetQueueRights
from ...application.commands.groups import CreateGroup, DeleteGroup, SetGroupMembers, UpdateGroup
from ...application.commands.queues import CreateQueue, DeleteQueue, UpdateQueue
from ...application.queries.access import ListGrants, ListGroups, ListQueues, QueueWithRights
from .schemas import (
    GrantResponse,
    GroupMembersRequest,
    GroupRequest,
    GroupResponse,
    QueueRequest,
    QueueResponse,
    QueueRightsRequest,
    RightsMatrixResponse,
)

Manager = Annotated[Member, member_with('queues.manage')]


def access_routes(bus: CommandBus) -> APIRouter:
    router = APIRouter(prefix='/tenants/{tenant_id}', tags=['access'])

    @router.get('/queues')
    async def queues(member: CurrentMember) -> list[QueueResponse]:
        """
        The queues the caller may see, with what they may do in each. Who manages queues sees every queue (with the
        rights their groups give); `queues.all` gives every right in every queue.
        """
        listed = await bus.query(
            ListQueues(
                tenant_id=member.tenant_id,
                user_id=member.user_id,
                all_queues=member.can('queues.all'),
                managing=member.can('queues.manage'),
            )
        )
        return [QueueResponse.of(item) for item in listed]

    @router.post('/queues', status_code=201, dependencies=[audited('queue.created')])
    async def create_queue(body: QueueRequest, request: Request, member: Manager) -> QueueResponse:
        queue = await bus.execute(CreateQueue(tenant_id=member.tenant_id, name=body.name, description=body.description))
        note_audit(request, target=queue.name)
        return QueueResponse.of(QueueWithRights(queue, frozenset()))

    @router.patch('/queues/{queue_id}', dependencies=[audited('queue.updated')])
    async def update_queue(queue_id: Id, body: QueueRequest, request: Request, member: Manager) -> QueueResponse:
        queue = await bus.execute(
            UpdateQueue(tenant_id=member.tenant_id, queue_id=queue_id, name=body.name, description=body.description)
        )
        note_audit(request, target=queue.name)
        return QueueResponse.of(QueueWithRights(queue, frozenset()))

    @router.delete(
        '/queues/{queue_id}', status_code=204, response_class=Response, dependencies=[audited('queue.deleted')]
    )
    async def delete_queue(queue_id: Id, request: Request, member: Manager) -> None:
        """With every group's rights on it."""
        queue = await bus.execute(DeleteQueue(tenant_id=member.tenant_id, queue_id=queue_id))
        note_audit(request, target=queue.name)

    @router.get('/groups')
    async def groups(member: Manager) -> list[GroupResponse]:
        return [GroupResponse.of(group) for group in await bus.query(ListGroups(member.tenant_id))]

    @router.post('/groups', status_code=201, dependencies=[audited('group.created')])
    async def create_group(body: GroupRequest, request: Request, member: Manager) -> GroupResponse:
        group = await bus.execute(CreateGroup(tenant_id=member.tenant_id, name=body.name, description=body.description))
        note_audit(request, target=group.name)
        return GroupResponse.of(group)

    @router.patch('/groups/{group_id}', dependencies=[audited('group.updated')])
    async def update_group(group_id: Id, body: GroupRequest, request: Request, member: Manager) -> GroupResponse:
        group = await bus.execute(
            UpdateGroup(tenant_id=member.tenant_id, group_id=group_id, name=body.name, description=body.description)
        )
        note_audit(request, target=group.name)
        return GroupResponse.of(group)

    @router.put('/groups/{group_id}/members', dependencies=[audited('group.members_changed')])
    async def set_members(group_id: Id, body: GroupMembersRequest, request: Request, member: Manager) -> GroupResponse:
        """Exactly these members of the organization are in the group afterwards."""
        group = await bus.execute(
            SetGroupMembers(tenant_id=member.tenant_id, group_id=group_id, user_ids=tuple(body.user_ids))
        )
        note_audit(request, target=group.name)
        return GroupResponse.of(group)

    @router.delete(
        '/groups/{group_id}', status_code=204, response_class=Response, dependencies=[audited('group.deleted')]
    )
    async def delete_group(group_id: Id, request: Request, member: Manager) -> None:
        group = await bus.execute(DeleteGroup(tenant_id=member.tenant_id, group_id=group_id))
        note_audit(request, target=group.name)

    @router.get('/queue-rights')
    async def rights(member: Manager) -> RightsMatrixResponse:
        """The matrix: what each group may do in each queue, the rights there are and the ready-made levels."""
        return RightsMatrixResponse.of(await bus.query(ListGrants(member.tenant_id)), PRESETS)

    @router.put('/queue-rights', dependencies=[audited('queue_rights.changed')])
    async def set_rights(body: QueueRightsRequest, request: Request, member: Manager) -> GrantResponse:
        """What a group may do in a queue from now on; no rights take them away."""
        grant = await bus.execute(
            SetQueueRights(
                tenant_id=member.tenant_id, group_id=body.group_id, queue_id=body.queue_id, rights=tuple(body.rights)
            )
        )
        note_audit(request, target=f'{grant.group_id} → {grant.queue_id}')
        return GrantResponse.of(grant)

    return router
