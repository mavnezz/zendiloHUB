from pathlib import Path

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.database.migration import sql_migrations
from zendilohub.core.events.integration_events import MemberRemoved, TenantDeleted, UserDeleted
from zendilohub.core.module import AppModule, ModuleContext

from .application.commands.assist import Assist, AssistantStatus, AssistantStatusHandler, AssistHandler
from .application.commands.automation import (
    ApplyAutomation,
    ApplyAutomationHandler,
    ExcerptOf,
    ExcerptOfHandler,
    FactsOf,
    FactsOfHandler,
    FindTickets,
    FindTicketsHandler,
)
from .application.commands.email import (
    MarkSent,
    MarkSentHandler,
    OutgoingOf,
    OutgoingOfHandler,
    ReceiveEmail,
    ReceiveEmailHandler,
    ThreadEmail,
    ThreadEmailHandler,
)
from .application.commands.fields import (
    AddChecklistItem,
    AddChecklistItemHandler,
    BeHere,
    BeHereHandler,
    ChangeChecklistItem,
    ChangeChecklistItemHandler,
    Checklist,
    ChecklistHandler,
    DeleteField,
    DeleteFieldHandler,
    ListFields,
    ListFieldsHandler,
    SaveField,
    SaveFieldHandler,
)
from .application.commands.forget import (
    CloseDueTickets,
    CloseDueTicketsHandler,
    ForgetMember,
    ForgetMemberHandler,
    ForgetTenant,
    ForgetTenantHandler,
)
from .application.commands.messages import AddMessage, AddMessageHandler
from .application.commands.portal import (
    PortalOpen,
    PortalOpenHandler,
    PortalReply,
    PortalReplyHandler,
    PortalThreadHandler,
    PortalThreadQuery,
    PortalTickets,
    PortalTicketsHandler,
)
from .application.commands.relations import (
    LinkTickets,
    LinkTicketsHandler,
    MergeTicket,
    MergeTicketHandler,
    RecordTime,
    RecordTimeHandler,
    SplitTicket,
    SplitTicketHandler,
    UnlinkTickets,
    UnlinkTicketsHandler,
    Watch,
    WatchHandler,
)
from .application.commands.tickets import (
    BulkUpdate,
    BulkUpdateHandler,
    CreateTicket,
    CreateTicketHandler,
    DeleteTicket,
    DeleteTicketHandler,
    UpdateTicket,
    UpdateTicketHandler,
)
from .application.queries.tickets import (
    Assignees,
    AssigneesHandler,
    CountTickets,
    CountTicketsHandler,
    FindTicketByNumber,
    FindTicketByNumberHandler,
    GetTicket,
    GetTicketHandler,
    ListMessages,
    ListMessagesHandler,
    SearchTickets,
    SearchTicketsHandler,
    SimilarTickets,
    SimilarTicketsHandler,
    TicketHistory,
    TicketHistoryHandler,
    TicketTime,
    TicketTimeHandler,
    TicketUsageHandler,
    TicketUsageQuery,
)
from .application.services.desk import Desk, TimeKeeper
from .domain.ports.services import TicketWriter
from .infrastructure.claude_writer import ClaudeWriter, NoWriter
from .infrastructure.contract_adapters import (
    BusTicketAutomation,
    BusTicketInbox,
    BusTicketPortal,
    BusTicketUsage,
    ContractCustomers,
    ContractQueueRights,
)
from .infrastructure.postgres_tickets import (
    PostgresChecklistRepository,
    PostgresFieldRepository,
    PostgresHistoryRepository,
    PostgresLinkRepository,
    PostgresMessageRepository,
    PostgresTicketRepository,
    PostgresTimeRepository,
    PostgresWatcherRepository,
)
from .infrastructure.redis_presence import RedisPresence
from .ui.api.routes import ticket_routes

MIGRATIONS = Path(__file__).parent / 'infrastructure' / 'migrations'
CLOSE_DUE_EVERY_SECONDS = 60


def create_tickets_module(context: ModuleContext, writer: TicketWriter | None = None) -> AppModule:
    """
    Tickets and their messages, history, tags, watchers, links and time. Who may do what with a ticket comes from the
    access module's rights in its queue (`QueueAccess` contract); customers come from the `Contacts` contract.
    """
    db = context.db
    tickets = PostgresTicketRepository(db)
    messages = PostgresMessageRepository(db)
    history = PostgresHistoryRepository(db)
    watchers = PostgresWatcherRepository(db)
    links = PostgresLinkRepository(db)
    times = PostgresTimeRepository(db)
    rights = ContractQueueRights(context.contracts)
    customers = ContractCustomers(context.contracts)
    desk = Desk(tickets, history, rights, context.events, context.ids, context.clock)
    time = TimeKeeper(desk, times)
    fields = PostgresFieldRepository(db)
    checklist = PostgresChecklistRepository(db)
    update = UpdateTicketHandler(desk, customers, db, fields)
    assistant = writer or _writer(context)
    bus = (
        CommandBus()
        .register(CreateTicket, CreateTicketHandler(desk, messages, customers, db, time))
        .register(UpdateTicket, update)
        .register(BulkUpdate, BulkUpdateHandler(update))
        .register(DeleteTicket, DeleteTicketHandler(desk))
        .register(AddMessage, AddMessageHandler(desk, messages, watchers, time, db))
        .register(Watch, WatchHandler(desk, watchers))
        .register(LinkTickets, LinkTicketsHandler(desk, links, db))
        .register(UnlinkTickets, UnlinkTicketsHandler(desk, links))
        .register(MergeTicket, MergeTicketHandler(desk, messages, watchers, links, db))
        .register(SplitTicket, SplitTicketHandler(desk, messages, links, db))
        .register(RecordTime, RecordTimeHandler(desk, time))
        .register(ForgetMember, ForgetMemberHandler(tickets, watchers, desk))
        .register(ForgetTenant, ForgetTenantHandler(tickets))
        .register(CloseDueTickets, CloseDueTicketsHandler(desk, db))
        .register(SearchTickets, SearchTicketsHandler(desk, customers))
        .register(CountTickets, CountTicketsHandler(desk))
        .register(GetTicket, GetTicketHandler(desk, watchers, links, times))
        .register(FindTicketByNumber, FindTicketByNumberHandler(desk))
        .register(ListMessages, ListMessagesHandler(desk, messages))
        .register(TicketHistory, TicketHistoryHandler(desk))
        .register(TicketTime, TicketTimeHandler(desk, times))
        .register(Assignees, AssigneesHandler(desk))
        .register(SimilarTickets, SimilarTicketsHandler(desk))
        .register(AssistantStatus, AssistantStatusHandler(assistant))
        .register(Assist, AssistHandler(desk, messages, customers, assistant, context.rate_limiter))
        .register(PortalTickets, PortalTicketsHandler(desk))
        .register(PortalThreadQuery, PortalThreadHandler(desk, messages))
        .register(PortalReply, PortalReplyHandler(desk, messages, db))
        .register(PortalOpen, PortalOpenHandler(desk, messages, db))
        .register(TicketUsageQuery, TicketUsageHandler(desk))
        .register(ReceiveEmail, ReceiveEmailHandler(desk, messages, customers, db))
        .register(ThreadEmail, ThreadEmailHandler(desk, messages))
        .register(OutgoingOf, OutgoingOfHandler(desk, messages, customers))
        .register(MarkSent, MarkSentHandler(messages))
        .register(SaveField, SaveFieldHandler(fields, context.ids, context.clock))
        .register(DeleteField, DeleteFieldHandler(fields))
        .register(ListFields, ListFieldsHandler(fields))
        .register(AddChecklistItem, AddChecklistItemHandler(desk, checklist))
        .register(ChangeChecklistItem, ChangeChecklistItemHandler(desk, checklist, db))
        .register(Checklist, ChecklistHandler(desk, checklist))
        .register(BeHere, BeHereHandler(desk, RedisPresence(context.redis, context.clock)))
        .register(FactsOf, FactsOfHandler(desk, watchers, customers))
        .register(FindTickets, FindTicketsHandler(desk))
        .register(ApplyAutomation, ApplyAutomationHandler(desk, messages, db))
        .register(ExcerptOf, ExcerptOfHandler(messages))
    )

    async def member_removed(event: MemberRemoved) -> None:
        await bus.execute(ForgetMember(event.tenant_id, event.user_id))

    async def user_deleted(event: UserDeleted) -> None:
        await bus.execute(ForgetMember(None, event.user_id))

    async def tenant_deleted(event: TenantDeleted) -> None:
        await bus.execute(ForgetTenant(event.tenant_id))

    context.events.subscribe(MemberRemoved, member_removed)
    context.events.subscribe(UserDeleted, user_deleted)
    context.events.subscribe(TenantDeleted, tenant_deleted)
    context.contracts.ticket_usage.provide(BusTicketUsage(bus))
    context.contracts.ticket_inbox.provide(BusTicketInbox(bus))
    context.contracts.ticket_automation.provide(BusTicketAutomation(bus))
    context.contracts.ticket_portal.provide(BusTicketPortal(bus))
    context.scheduler.every(CLOSE_DUE_EVERY_SECONDS, 'tickets.close_due', lambda: bus.execute(CloseDueTickets()))

    return AppModule(
        name='tickets', migrations=sql_migrations(MIGRATIONS), routers=[ticket_routes(bus, context.contracts)]
    )


def _writer(context: ModuleContext) -> TicketWriter:
    key = context.config.anthropic_api_key
    if key is None:
        return NoWriter()
    import anthropic

    return ClaudeWriter(anthropic.AsyncAnthropic(api_key=key, timeout=90.0, max_retries=2), context.config.ai_model)
