from pathlib import Path

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.database.migration import sql_migrations
from zendilohub.core.events.integration_events import (
    MessageAdded,
    SlaBreached,
    TenantDeleted,
    TicketChanged,
    TicketCreated,
)
from zendilohub.core.module import AppModule, ModuleContext

from .application.commands.reports import (
    ForgetTenant,
    ForgetTenantHandler,
    GetReport,
    GetReportHandler,
    Track,
    TrackHandler,
)
from .infrastructure.contract_adapters import ContractTickets
from .infrastructure.postgres_reports import PostgresReportRepository
from .ui.api.routes import report_routes

MIGRATIONS = Path(__file__).parent / 'infrastructure' / 'migrations'


def create_reporting_module(context: ModuleContext) -> AppModule:
    """Key figures: tickets opened and closed, response and solution times, missed service levels, load by queue."""
    reports = PostgresReportRepository(context.db)
    bus = (
        CommandBus()
        .register(Track, TrackHandler(reports, ContractTickets(context.contracts), context.clock))
        .register(GetReport, GetReportHandler(reports))
        .register(ForgetTenant, ForgetTenantHandler(reports))
    )

    async def created(event: TicketCreated) -> None:
        await bus.execute(Track(tenant_id=event.tenant_id, ticket_id=event.ticket_id))

    async def changed(event: TicketChanged) -> None:
        await bus.execute(Track(tenant_id=event.tenant_id, ticket_id=event.ticket_id))

    async def message_added(event: MessageAdded) -> None:
        if event.kind == 'public' and event.direction == 'out':
            await bus.execute(Track(tenant_id=event.tenant_id, ticket_id=event.ticket_id, responded=True))

    async def breached(event: SlaBreached) -> None:
        await bus.execute(Track(tenant_id=event.tenant_id, ticket_id=event.ticket_id, breached=True))

    async def tenant_deleted(event: TenantDeleted) -> None:
        await bus.execute(ForgetTenant(event.tenant_id))

    context.events.subscribe(TicketCreated, created)
    context.events.subscribe(TicketChanged, changed)
    context.events.subscribe(MessageAdded, message_added)
    context.events.subscribe(SlaBreached, breached)
    context.events.subscribe(TenantDeleted, tenant_deleted)
    return AppModule(name='reporting', migrations=sql_migrations(MIGRATIONS), routers=[report_routes(bus)])
