from pathlib import Path

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.database.migration import sql_migrations
from zendilohub.core.events.integration_events import (
    MessageAdded,
    QueueDeleted,
    SlaBreached,
    TenantDeleted,
    TicketChanged,
    TicketCreated,
)
from zendilohub.core.module import AppModule, ModuleContext

from .application.commands.webhooks import (
    DELIVER_TASK,
    Announce,
    AnnounceHandler,
    DeleteWebhook,
    DeleteWebhookHandler,
    Deliver,
    DeliverHandler,
    ForgetQueue,
    ForgetQueueHandler,
    ForgetTenant,
    ForgetTenantHandler,
    ListDeliveries,
    ListDeliveriesHandler,
    ListWebhooks,
    ListWebhooksHandler,
    SaveWebhook,
    SaveWebhookHandler,
)
from .infrastructure.contract_adapters import ContractTickets
from .infrastructure.postgres_webhooks import PostgresWebhookRepository
from .ui.api.routes import integration_routes

MIGRATIONS = Path(__file__).parent / 'infrastructure' / 'migrations'


def create_integrations_module(context: ModuleContext) -> AppModule:
    """
    Outgoing webhooks: other systems (e.g. zendilo.ai, a CRM) hear about new tickets, changes, messages and missed
    service levels, signed and retried; Slack and Microsoft Teams get them as chat messages, optionally only of some
    queues.
    """
    webhooks = PostgresWebhookRepository(context.db)
    tickets = ContractTickets(context.contracts)
    bus = (
        CommandBus()
        .register(SaveWebhook, SaveWebhookHandler(webhooks, tickets, context.cipher, context.ids, context.clock))
        .register(DeleteWebhook, DeleteWebhookHandler(webhooks))
        .register(
            Announce,
            AnnounceHandler(
                webhooks,
                tickets,
                context.jobs,
                context.ids,
                context.clock,
                link_base=context.config.public_url or '',
            ),
        )
        .register(
            Deliver,
            DeliverHandler(webhooks, context.cipher, context.fetcher, context.jobs, context.ids, context.clock),
        )
        .register(ListWebhooks, ListWebhooksHandler(webhooks))
        .register(ListDeliveries, ListDeliveriesHandler(webhooks))
        .register(ForgetTenant, ForgetTenantHandler(webhooks))
        .register(ForgetQueue, ForgetQueueHandler(webhooks))
    )

    async def created(event: TicketCreated) -> None:
        await bus.execute(Announce(tenant_id=event.tenant_id, event='ticket.created', ticket_id=event.ticket_id))

    async def changed(event: TicketChanged) -> None:
        await bus.execute(
            Announce(
                tenant_id=event.tenant_id,
                event='ticket.changed',
                ticket_id=event.ticket_id,
                data={'changes': [{'field': f, 'old': old, 'new': new} for f, old, new in event.changes]},
            )
        )

    async def message_added(event: MessageAdded) -> None:
        await bus.execute(
            Announce(
                tenant_id=event.tenant_id,
                event='message.added',
                ticket_id=event.ticket_id,
                data={'message': {'id': event.message_id, 'kind': event.kind, 'direction': event.direction}},
            )
        )

    async def breached(event: SlaBreached) -> None:
        await bus.execute(
            Announce(
                tenant_id=event.tenant_id, event='sla.breached', ticket_id=event.ticket_id, data={'kind': event.kind}
            )
        )

    async def tenant_deleted(event: TenantDeleted) -> None:
        await bus.execute(ForgetTenant(event.tenant_id))

    context.events.subscribe(TicketCreated, created)
    context.events.subscribe(TicketChanged, changed)
    context.events.subscribe(MessageAdded, message_added)
    context.events.subscribe(SlaBreached, breached)

    async def queue_deleted(event: QueueDeleted) -> None:
        await bus.execute(ForgetQueue(event.tenant_id, event.queue_id))

    context.events.subscribe(TenantDeleted, tenant_deleted)
    context.events.subscribe(QueueDeleted, queue_deleted)

    async def deliver(tenant_id: str, webhook_id: str, body: str, attempt: str = '1') -> None:
        await bus.execute(Deliver(tenant_id, webhook_id, body, int(attempt)))

    return AppModule(
        name='integrations',
        migrations=sql_migrations(MIGRATIONS),
        routers=[integration_routes(bus)],
        tasks={DELIVER_TASK: deliver},
    )
