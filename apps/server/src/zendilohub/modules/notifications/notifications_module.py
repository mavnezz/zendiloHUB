from pathlib import Path

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.database.migration import sql_migrations
from zendilohub.core.events.integration_events import (
    MemberRemoved,
    MessageAdded,
    QueueDeleted,
    SlaBreached,
    TenantDeleted,
    TicketChanged,
    TicketCreated,
    UserDeleted,
)
from zendilohub.core.module import AppModule, ModuleContext

from .application.commands.notify import (
    FollowersOf,
    FollowersOfHandler,
    FollowQueues,
    FollowQueuesHandler,
    Forget,
    ForgetHandler,
    ForgetQueue,
    ForgetQueueHandler,
    GetFollowedQueues,
    GetFollowedQueuesHandler,
    GetSettings,
    GetSettingsHandler,
    ListNotifications,
    ListNotificationsHandler,
    MarkRead,
    MarkReadHandler,
    Notify,
    NotifyHandler,
    SaveSettings,
    SaveSettingsHandler,
)
from .infrastructure.contract_adapters import ContractDirectory
from .infrastructure.postgres_notifications import PostgresNotificationRepository
from .ui.api.routes import notification_routes

MIGRATIONS = Path(__file__).parent / 'infrastructure' / 'migrations'


def create_notifications_module(context: ModuleContext) -> AppModule:
    """
    What members hear about tickets: assigned to them, mentioned, new messages in tickets they own or watch, missed
    service levels, new tickets in queues they follow. In the app, and by e-mail for those who want it.
    """
    notifications = PostgresNotificationRepository(context.db)
    directory = ContractDirectory(context.contracts)
    link_base = (context.config.public_url or '').rstrip('/')
    bus = (
        CommandBus()
        .register(
            Notify, NotifyHandler(notifications, directory, context.mailer, context.ids, context.clock, link_base)
        )
        .register(ListNotifications, ListNotificationsHandler(notifications))
        .register(MarkRead, MarkReadHandler(notifications, context.clock))
        .register(GetSettings, GetSettingsHandler(notifications))
        .register(SaveSettings, SaveSettingsHandler(notifications))
        .register(Forget, ForgetHandler(notifications))
        .register(GetFollowedQueues, GetFollowedQueuesHandler(notifications))
        .register(FollowQueues, FollowQueuesHandler(notifications, directory))
        .register(FollowersOf, FollowersOfHandler(notifications, directory))
        .register(ForgetQueue, ForgetQueueHandler(notifications))
    )

    async def created(event: TicketCreated) -> None:
        followers = await bus.query(FollowersOf(tenant_id=event.tenant_id, queue_id=event.queue_id))
        if not followers:
            return
        facts = await directory.facts(event.tenant_id, event.ticket_id)
        await bus.execute(
            Notify(
                tenant_id=event.tenant_id,
                ticket_id=event.ticket_id,
                kind='created',
                user_ids=followers,
                actor_id=event.actor_id,
                actor=facts.customer_email if facts and event.actor_id is None else None,
            )
        )

    async def changed(event: TicketChanged) -> None:
        for field, _old, new in event.changes:
            if field == 'queue_id' and new:
                followers = await bus.query(FollowersOf(tenant_id=event.tenant_id, queue_id=new))
                await bus.execute(
                    Notify(
                        tenant_id=event.tenant_id,
                        ticket_id=event.ticket_id,
                        kind='moved',
                        user_ids=followers,
                        actor_id=event.actor_id,
                    )
                )
            if field == 'owner_id' and new:
                await bus.execute(
                    Notify(
                        tenant_id=event.tenant_id,
                        ticket_id=event.ticket_id,
                        kind='assigned',
                        user_ids=[new],
                        actor_id=event.actor_id,
                    )
                )

    async def message_added(event: MessageAdded) -> None:
        if event.first:
            return
        if event.mentions:
            await bus.execute(
                Notify(
                    tenant_id=event.tenant_id,
                    ticket_id=event.ticket_id,
                    kind='mentioned',
                    user_ids=list(event.mentions),
                    actor_id=event.author_id,
                )
            )
        facts = await directory.facts(event.tenant_id, event.ticket_id)
        if facts is None:
            return
        people = [each for each in (facts.owner_id, *facts.watchers) if each and each not in event.mentions]
        if event.direction == 'in':
            # Followers of the queue in mode `all` hear about every customer reply as well.
            followers = await bus.query(FollowersOf(tenant_id=event.tenant_id, queue_id=facts.queue_id, modes=('all',)))
            people += [each for each in followers if each not in people and each not in event.mentions]
        await bus.execute(
            Notify(
                tenant_id=event.tenant_id,
                ticket_id=event.ticket_id,
                kind='message',
                user_ids=people,
                actor_id=event.author_id if event.direction == 'out' else None,
                actor=facts.customer_email if event.direction == 'in' else None,
            )
        )

    async def breached(event: SlaBreached) -> None:
        facts = await directory.facts(event.tenant_id, event.ticket_id)
        if facts is not None:
            await bus.execute(
                Notify(
                    tenant_id=event.tenant_id,
                    ticket_id=event.ticket_id,
                    kind='sla_breached',
                    user_ids=[each for each in (facts.owner_id, facts.responsible_id) if each],
                )
            )

    async def member_removed(event: MemberRemoved) -> None:
        await bus.execute(Forget(event.tenant_id, event.user_id))

    async def user_deleted(event: UserDeleted) -> None:
        await bus.execute(Forget(None, event.user_id))

    async def tenant_deleted(event: TenantDeleted) -> None:
        await bus.execute(Forget(event.tenant_id))

    async def queue_deleted(event: QueueDeleted) -> None:
        await bus.execute(ForgetQueue(event.tenant_id, event.queue_id))

    context.events.subscribe(TicketCreated, created)
    context.events.subscribe(QueueDeleted, queue_deleted)
    context.events.subscribe(TicketChanged, changed)
    context.events.subscribe(MessageAdded, message_added)
    context.events.subscribe(SlaBreached, breached)
    context.events.subscribe(MemberRemoved, member_removed)
    context.events.subscribe(UserDeleted, user_deleted)
    context.events.subscribe(TenantDeleted, tenant_deleted)
    return AppModule(name='notifications', migrations=sql_migrations(MIGRATIONS), routers=[notification_routes(bus)])
