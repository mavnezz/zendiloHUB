from pathlib import Path

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.database.migration import sql_migrations
from zendilohub.core.events.integration_events import QueueDeleted, TenantDeleted
from zendilohub.core.module import AppModule, ModuleContext

from .application.commands.text_modules import (
    DeleteTextModule,
    DeleteTextModuleHandler,
    ForgetQueue,
    ForgetQueueHandler,
    ForgetTenant,
    ForgetTenantHandler,
    ListTextModules,
    ListTextModulesHandler,
    SaveTextModule,
    SaveTextModuleHandler,
)
from .infrastructure.postgres_text_modules import PostgresTextModuleRepository
from .ui.api.routes import knowledge_routes

MIGRATIONS = Path(__file__).parent / 'infrastructure' / 'migrations'


def create_knowledge_module(context: ModuleContext) -> AppModule:
    """Text modules for writing replies (`::keyword`), for every queue or only some."""
    modules = PostgresTextModuleRepository(context.db)
    bus = (
        CommandBus()
        .register(SaveTextModule, SaveTextModuleHandler(modules, context.ids, context.clock))
        .register(DeleteTextModule, DeleteTextModuleHandler(modules))
        .register(ListTextModules, ListTextModulesHandler(modules))
        .register(ForgetQueue, ForgetQueueHandler(modules))
        .register(ForgetTenant, ForgetTenantHandler(modules))
    )

    async def queue_deleted(event: QueueDeleted) -> None:
        await bus.execute(ForgetQueue(event.tenant_id, event.queue_id))

    async def tenant_deleted(event: TenantDeleted) -> None:
        await bus.execute(ForgetTenant(event.tenant_id))

    context.events.subscribe(QueueDeleted, queue_deleted)
    context.events.subscribe(TenantDeleted, tenant_deleted)
    return AppModule(name='knowledge', migrations=sql_migrations(MIGRATIONS), routers=[knowledge_routes(bus)])
