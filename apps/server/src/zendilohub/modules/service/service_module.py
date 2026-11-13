from pathlib import Path

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.database.migration import sql_migrations
from zendilohub.core.events.integration_events import MessageAdded, TenantDeleted, TicketChanged, TicketCreated
from zendilohub.core.module import AppModule, ModuleContext

from .application.commands.service import (
    CheckDeadlines,
    CheckDeadlinesHandler,
    ClockOf,
    ClockOfHandler,
    DeleteCalendar,
    DeleteCalendarHandler,
    DeletePolicy,
    DeletePolicyHandler,
    Escalations,
    EscalationsHandler,
    ForgetTenant,
    ForgetTenantHandler,
    GetSetup,
    GetSetupHandler,
    SaveCalendar,
    SaveCalendarHandler,
    SavePolicy,
    SavePolicyHandler,
    Track,
    TrackHandler,
)
from .infrastructure.contract_adapters import ContractTickets
from .infrastructure.postgres_service import PostgresServiceRepository
from .ui.api.routes import service_routes

MIGRATIONS = Path(__file__).parent / 'infrastructure' / 'migrations'
CHECK_EVERY_SECONDS = 60
TRACKED = frozenset({'queue_id', 'priority', 'state'})


def create_service_module(context: ModuleContext) -> AppModule:
    """
    Service levels (like OTOBO's and Zammad's SLAs): first response and solution times per queue and priority,
    counted in business hours with holidays; `SlaBreached` tells others (notifications) when one is missed.
    """
    service = PostgresServiceRepository(context.db)
    tickets = ContractTickets(context.contracts)
    bus = (
        CommandBus()
        .register(SaveCalendar, SaveCalendarHandler(service, context.ids, context.clock))
        .register(DeleteCalendar, DeleteCalendarHandler(service))
        .register(SavePolicy, SavePolicyHandler(service, context.ids, context.clock))
        .register(DeletePolicy, DeletePolicyHandler(service))
        .register(Track, TrackHandler(service, tickets, context.clock))
        .register(CheckDeadlines, CheckDeadlinesHandler(service, context.events, context.clock))
        .register(GetSetup, GetSetupHandler(service))
        .register(ClockOf, ClockOfHandler(service))
        .register(Escalations, EscalationsHandler(service, context.clock))
        .register(ForgetTenant, ForgetTenantHandler(service))
    )

    async def created(event: TicketCreated) -> None:
        await bus.execute(Track(tenant_id=event.tenant_id, ticket_id=event.ticket_id))

    async def changed(event: TicketChanged) -> None:
        if any(field in TRACKED for field, _old, _new in event.changes):
            await bus.execute(Track(tenant_id=event.tenant_id, ticket_id=event.ticket_id))

    async def message_added(event: MessageAdded) -> None:
        if event.kind == 'public' and event.direction == 'out':
            await bus.execute(Track(tenant_id=event.tenant_id, ticket_id=event.ticket_id, responded=True))

    async def tenant_deleted(event: TenantDeleted) -> None:
        await bus.execute(ForgetTenant(event.tenant_id))

    context.events.subscribe(TicketCreated, created)
    context.events.subscribe(TicketChanged, changed)
    context.events.subscribe(MessageAdded, message_added)
    context.events.subscribe(TenantDeleted, tenant_deleted)
    context.scheduler.every(CHECK_EVERY_SECONDS, 'service.deadlines', lambda: bus.execute(CheckDeadlines()))
    return AppModule(name='service', migrations=sql_migrations(MIGRATIONS), routers=[service_routes(bus)])
