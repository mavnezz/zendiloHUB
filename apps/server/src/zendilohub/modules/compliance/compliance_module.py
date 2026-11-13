import logging
from pathlib import Path

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.database.migration import sql_migrations
from zendilohub.core.events.integration_events import ActionPerformed, TenantDeleted, UserDeleted
from zendilohub.core.module import AppModule, ModuleContext

from .application.commands.audit import (
    ForgetActor,
    ForgetActorHandler,
    ForgetTenant,
    ForgetTenantHandler,
    PurgeAuditLog,
    PurgeAuditLogHandler,
    RecordAction,
    RecordActionHandler,
)
from .application.queries.audit_log import ListAuditLog, ListAuditLogHandler
from .infrastructure.postgres_audit import PostgresAuditRepository
from .ui.api.routes import audit_routes

MIGRATIONS = Path(__file__).parent / 'infrastructure' / 'migrations'

logger = logging.getLogger(__name__)


def create_compliance_module(context: ModuleContext) -> AppModule:
    """The audit log of every change, with retention; later data export and deletion periods (GDPR)."""
    entries = PostgresAuditRepository(context.db)
    bus = (
        CommandBus()
        .register(RecordAction, RecordActionHandler(entries, context.ids, context.clock))
        .register(PurgeAuditLog, PurgeAuditLogHandler(entries, context.clock))
        .register(ForgetTenant, ForgetTenantHandler(entries))
        .register(ForgetActor, ForgetActorHandler(entries))
        .register(ListAuditLog, ListAuditLogHandler(entries))
    )

    async def record(event: ActionPerformed) -> None:
        await bus.execute(
            RecordAction(
                action=event.action,
                tenant_id=event.tenant_id,
                target=event.target,
                actor_id=event.actor_id,
                actor_email=event.actor_email,
                succeeded=event.succeeded,
                status=event.status,
                client=event.client,
            )
        )

    async def forget_tenant(event: TenantDeleted) -> None:
        await bus.execute(ForgetTenant(event.tenant_id))

    async def forget_actor(event: UserDeleted) -> None:
        await bus.execute(ForgetActor(event.user_id, event.email))

    context.events.subscribe(ActionPerformed, record)
    context.events.subscribe(TenantDeleted, forget_tenant)
    context.events.subscribe(UserDeleted, forget_actor)

    async def purge() -> None:
        purged = await bus.execute(PurgeAuditLog(context.config.audit_retention_days))
        if purged:
            logger.info('Purged old audit log entries', extra={'count': purged})

    context.scheduler.every(6 * 60 * 60, 'compliance.purge-audit-log', purge)

    return AppModule(name='compliance', migrations=sql_migrations(MIGRATIONS), routers=[audit_routes(bus)])
