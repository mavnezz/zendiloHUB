from pathlib import Path

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.database.migration import sql_migrations
from zendilohub.core.events.integration_events import MemberRemoved, TenantDeleted, UserDeleted
from zendilohub.core.module import AppModule, ModuleContext

from .application.commands.connections import (
    Authenticate,
    AuthenticateHandler,
    Connect,
    ConnectHandler,
    Disconnect,
    DisconnectHandler,
    Forget,
    ForgetHandler,
    ListConnections,
    ListConnectionsHandler,
)
from .infrastructure.postgres_connections import ContractMembers, PostgresConnectionRepository
from .ui.api.routes import connection_routes, mcp_routes

MIGRATIONS = Path(__file__).parent / 'infrastructure' / 'migrations'


def create_mcp_module(context: ModuleContext) -> AppModule:
    """
    The MCP server: AI assistants (Claude, ChatGPT, …) a member connects work with tickets for them, through the same
    API and with the same rights. Customer text is marked as data, never as instructions.
    """
    connections = PostgresConnectionRepository(context.db)
    bus = (
        CommandBus()
        .register(Connect, ConnectHandler(connections, context.ids, context.clock))
        .register(Disconnect, DisconnectHandler(connections))
        .register(ListConnections, ListConnectionsHandler(connections))
        .register(Authenticate, AuthenticateHandler(connections, ContractMembers(context.contracts), context.clock))
        .register(Forget, ForgetHandler(connections))
    )

    async def member_removed(event: MemberRemoved) -> None:
        await bus.execute(Forget(event.tenant_id, event.user_id))

    async def user_deleted(event: UserDeleted) -> None:
        await bus.execute(Forget(None, event.user_id))

    async def tenant_deleted(event: TenantDeleted) -> None:
        await bus.execute(Forget(event.tenant_id, None))

    context.events.subscribe(MemberRemoved, member_removed)
    context.events.subscribe(UserDeleted, user_deleted)
    context.events.subscribe(TenantDeleted, tenant_deleted)
    return AppModule(
        name='mcp',
        migrations=sql_migrations(MIGRATIONS),
        routers=[connection_routes(bus)],
        root_routers=[mcp_routes(bus, context.rate_limiter)],
    )
