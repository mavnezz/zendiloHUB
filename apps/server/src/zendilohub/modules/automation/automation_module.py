from pathlib import Path

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.database.migration import sql_migrations
from zendilohub.core.events.integration_events import MessageAdded, TenantDeleted, TicketChanged, TicketCreated
from zendilohub.core.module import AppModule, ModuleContext

from .application.commands.rules import (
    DeleteRule,
    DeleteRuleHandler,
    ForgetTenant,
    ForgetTenantHandler,
    ListRules,
    ListRulesHandler,
    RunSchedules,
    RunSchedulesHandler,
    RunTriggers,
    RunTriggersHandler,
    SaveRule,
    SaveRuleHandler,
)
from .infrastructure.contract_adapters import ContractTickets
from .infrastructure.postgres_rules import PostgresRuleRepository
from .ui.api.routes import automation_routes

MIGRATIONS = Path(__file__).parent / 'infrastructure' / 'migrations'
SCHEDULES_EVERY_SECONDS = 5 * 60


def create_automation_module(context: ModuleContext) -> AppModule:
    """
    Macros, triggers (when a ticket is created, the customer replies or someone changes it) and scheduled jobs
    (every five minutes). Rules change tickets through the tickets module's `TicketAutomation` contract; what they
    change does not start triggers again.
    """
    db = context.db
    rules = PostgresRuleRepository(db)
    tickets = ContractTickets(context.contracts)
    bus = (
        CommandBus()
        .register(SaveRule, SaveRuleHandler(rules, context.ids, context.clock))
        .register(DeleteRule, DeleteRuleHandler(rules))
        .register(ListRules, ListRulesHandler(rules))
        .register(RunTriggers, RunTriggersHandler(rules, tickets, db))
        .register(RunSchedules, RunSchedulesHandler(rules, tickets, db, context.clock))
        .register(ForgetTenant, ForgetTenantHandler(rules))
    )

    async def created(event: TicketCreated) -> None:
        await bus.execute(RunTriggers(tenant_id=event.tenant_id, ticket_id=event.ticket_id, event='created'))

    async def message_added(event: MessageAdded) -> None:
        if event.direction == 'in' and not event.automated and not event.first:
            await bus.execute(
                RunTriggers(tenant_id=event.tenant_id, ticket_id=event.ticket_id, event='customer_replied')
            )

    async def changed(event: TicketChanged) -> None:
        if not event.automated:
            await bus.execute(RunTriggers(tenant_id=event.tenant_id, ticket_id=event.ticket_id, event='updated'))

    async def tenant_deleted(event: TenantDeleted) -> None:
        await bus.execute(ForgetTenant(event.tenant_id))

    context.events.subscribe(TicketCreated, created)
    context.events.subscribe(MessageAdded, message_added)
    context.events.subscribe(TicketChanged, changed)
    context.events.subscribe(TenantDeleted, tenant_deleted)
    context.scheduler.every(SCHEDULES_EVERY_SECONDS, 'automation.schedules', lambda: bus.execute(RunSchedules()))

    return AppModule(name='automation', migrations=sql_migrations(MIGRATIONS), routers=[automation_routes(bus)])
