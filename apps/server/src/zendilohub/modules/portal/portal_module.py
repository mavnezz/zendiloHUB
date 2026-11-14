from pathlib import Path

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.database.migration import sql_migrations
from zendilohub.core.events.integration_events import TenantDeleted
from zendilohub.core.module import AppModule, ModuleContext

from .application.commands.portal import (
    Answer,
    AnswerHandler,
    ForgetTenant,
    ForgetTenantHandler,
    GetSettings,
    GetSettingsHandler,
    MyThread,
    MyThreadHandler,
    MyTickets,
    MyTicketsHandler,
    OpenTicket,
    OpenTicketHandler,
    RequestLink,
    RequestLinkHandler,
    SaveSettings,
    SaveSettingsHandler,
    SignOut,
    SignOutHandler,
    Verify,
    VerifyHandler,
    WhoIs,
    WhoIsHandler,
)
from .infrastructure.storage import ContractCustomers, ContractTickets, PostgresPortalRepository
from .ui.api.routes import portal_routes, portal_settings_routes

MIGRATIONS = Path(__file__).parent / 'infrastructure' / 'migrations'


def create_portal_module(context: ModuleContext) -> AppModule:
    """
    The customer portal (like OTOBO's and Zammad's): contacts sign in with a link sent to their e-mail address, see
    their tickets (and their company's, if allowed), answer and open new ones. They never see internal notes.
    """
    portal = PostgresPortalRepository(context.db)
    customers = ContractCustomers(context.contracts)
    tickets = ContractTickets(context.contracts)
    clock = context.clock
    bus = (
        CommandBus()
        .register(SaveSettings, SaveSettingsHandler(portal))
        .register(GetSettings, GetSettingsHandler(portal))
        .register(RequestLink, RequestLinkHandler(portal, customers, context.mailer, context.rate_limiter, clock))
        .register(Verify, VerifyHandler(portal, customers, clock))
        .register(WhoIs, WhoIsHandler(portal, customers, clock))
        .register(SignOut, SignOutHandler(portal))
        .register(MyTickets, MyTicketsHandler(tickets))
        .register(MyThread, MyThreadHandler(tickets))
        .register(Answer, AnswerHandler(tickets))
        .register(OpenTicket, OpenTicketHandler(tickets))
        .register(ForgetTenant, ForgetTenantHandler(portal))
    )

    async def tenant_deleted(event: TenantDeleted) -> None:
        await bus.execute(ForgetTenant(event.tenant_id))

    context.events.subscribe(TenantDeleted, tenant_deleted)
    return AppModule(
        name='portal',
        migrations=sql_migrations(MIGRATIONS),
        routers=[portal_settings_routes(bus), portal_routes(bus, context.config)],
    )
