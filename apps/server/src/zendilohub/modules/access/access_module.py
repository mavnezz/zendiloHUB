from pathlib import Path

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.database.migration import sql_migrations
from zendilohub.core.events.integration_events import MemberRemoved, TenantDeleted, UserDeleted
from zendilohub.core.module import AppModule, ModuleContext

from .application.commands.forget import (
    ForgetMember,
    ForgetMemberHandler,
    ForgetTenant,
    ForgetTenantHandler,
    ForgetUser,
    ForgetUserHandler,
)
from .application.commands.grants import SetQueueRights, SetQueueRightsHandler
from .application.commands.groups import (
    CreateGroup,
    CreateGroupHandler,
    DeleteGroup,
    DeleteGroupHandler,
    SetGroupMembers,
    SetGroupMembersHandler,
    UpdateGroup,
    UpdateGroupHandler,
)
from .application.commands.queues import (
    CreateQueue,
    CreateQueueHandler,
    DeleteQueue,
    DeleteQueueHandler,
    UpdateQueue,
    UpdateQueueHandler,
)
from .application.queries.access import (
    ListGrants,
    ListGrantsHandler,
    ListGroups,
    ListGroupsHandler,
    ListQueues,
    ListQueuesHandler,
    RightsOf,
    RightsOfHandler,
)
from .infrastructure.contract_adapters import BusQueueAccess, TenancyMembers
from .infrastructure.postgres_access import (
    PostgresGrantRepository,
    PostgresGroupRepository,
    PostgresQueueRepository,
    PostgresTenantData,
)
from .ui.api.routes import access_routes

MIGRATIONS = Path(__file__).parent / 'infrastructure' / 'migrations'


def create_access_module(context: ModuleContext) -> AppModule:
    """
    Who may do what in which queue: queues, groups of people and the rights of each group in each queue. Other
    modules ask through the `QueueAccess` contract.
    """
    db, clock, ids, events = context.db, context.clock, context.ids, context.events
    queues = PostgresQueueRepository(db)
    groups = PostgresGroupRepository(db)
    grants = PostgresGrantRepository(db)
    bus = (
        CommandBus()
        .register(CreateQueue, CreateQueueHandler(queues, ids, clock))
        .register(UpdateQueue, UpdateQueueHandler(queues, clock))
        .register(DeleteQueue, DeleteQueueHandler(queues, db, events))
        .register(CreateGroup, CreateGroupHandler(groups, ids, clock))
        .register(UpdateGroup, UpdateGroupHandler(groups, clock))
        .register(SetGroupMembers, SetGroupMembersHandler(groups, TenancyMembers(context.contracts), clock))
        .register(DeleteGroup, DeleteGroupHandler(groups))
        .register(SetQueueRights, SetQueueRightsHandler(queues, groups, grants))
        .register(ForgetMember, ForgetMemberHandler(groups))
        .register(ForgetUser, ForgetUserHandler(groups))
        .register(ForgetTenant, ForgetTenantHandler(PostgresTenantData(db)))
        .register(ListQueues, ListQueuesHandler(queues, grants))
        .register(ListGroups, ListGroupsHandler(groups))
        .register(ListGrants, ListGrantsHandler(grants))
        .register(RightsOf, RightsOfHandler(queues, grants))
    )

    async def member_removed(event: MemberRemoved) -> None:
        await bus.execute(ForgetMember(event.tenant_id, event.user_id))

    async def user_deleted(event: UserDeleted) -> None:
        await bus.execute(ForgetUser(event.user_id))

    async def tenant_deleted(event: TenantDeleted) -> None:
        await bus.execute(ForgetTenant(event.tenant_id))

    events.subscribe(MemberRemoved, member_removed)
    events.subscribe(UserDeleted, user_deleted)
    events.subscribe(TenantDeleted, tenant_deleted)
    context.contracts.queue_access.provide(BusQueueAccess(bus))

    return AppModule(name='access', migrations=sql_migrations(MIGRATIONS), routers=[access_routes(bus)])
