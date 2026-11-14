from pathlib import Path

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.database.migration import sql_migrations
from zendilohub.core.events.integration_events import (
    MemberRemoved,
    MessageAdded,
    QueueDeleted,
    TenantDeleted,
    UserDeleted,
)
from zendilohub.core.module import AppModule, ModuleContext

from .application.commands.accounts import (
    CreateAccount,
    CreateAccountHandler,
    DeleteAccount,
    DeleteAccountHandler,
    TestAccount,
    TestAccountHandler,
    UpdateAccount,
    UpdateAccountHandler,
    Vault,
)
from .application.commands.inbound import (
    FETCH_TASK,
    AutoReplier,
    DeleteFailedEmail,
    DeleteFailedEmailHandler,
    FetchAccount,
    FetchAccountHandler,
    FetchDue,
    FetchDueHandler,
    ProcessEmail,
    ProcessEmailHandler,
    RetryFailedEmail,
    RetryFailedEmailHandler,
)
from .application.commands.oauth import (
    FinishConnect,
    FinishConnectHandler,
    MailProviders,
    MailProvidersHandler,
    StartConnect,
    StartConnectHandler,
)
from .application.commands.outbound import (
    SEND_TASK,
    QueueReply,
    QueueReplyHandler,
    ResendReply,
    ResendReplyHandler,
    SendReply,
    SendReplyHandler,
)
from .application.commands.settings import (
    DeleteFilter,
    DeleteFilterHandler,
    DeleteTemplate,
    DeleteTemplateHandler,
    ForgetMember,
    ForgetMemberHandler,
    ForgetQueue,
    ForgetQueueHandler,
    ForgetTenant,
    ForgetTenantHandler,
    ReorderFilters,
    ReorderFiltersHandler,
    SaveFilter,
    SaveFilterHandler,
    SaveTemplate,
    SaveTemplateHandler,
    SetPersonal,
    SetPersonalHandler,
    SetQueueChannel,
    SetQueueChannelHandler,
)
from .application.commands.smime import (
    AddCertificate,
    AddCertificateHandler,
    DeleteCertificate,
    DeleteCertificateHandler,
    ListCertificates,
    ListCertificatesHandler,
)
from .application.queries.channels import (
    GetPersonal,
    GetPersonalHandler,
    ListAccounts,
    ListAccountsHandler,
    ListFailedEmails,
    ListFailedEmailsHandler,
    ListFilters,
    ListFiltersHandler,
    ListQueueChannels,
    ListQueueChannelsHandler,
    ListTemplates,
    ListTemplatesHandler,
    ReplyDraft,
    ReplyDraftHandler,
    TicketDeliveries,
    TicketDeliveriesHandler,
)
from .application.services.smime import Smime
from .application.services.writer import Writer
from .domain.ports.services import Mailbox, OAuthProviders, Outbox
from .infrastructure.contract_adapters import ContractNames, ContractTickets
from .infrastructure.mail_servers import ImapMailbox, Nh3Cleaner, SmtpOutbox
from .infrastructure.oauth_providers import HttpOAuthProviders
from .infrastructure.postgres_channels import (
    PostgresAccountRepository,
    PostgresCertificateRepository,
    PostgresConnectRequestRepository,
    PostgresDeliveryRepository,
    PostgresFailedEmailRepository,
    PostgresFilterRepository,
    PostgresPersonalRepository,
    PostgresQueueChannelRepository,
    PostgresTemplateRepository,
)
from .infrastructure.smime import CryptographySmime
from .ui.api.routes import channel_routes, oauth_callback_routes
from .ui.api.smime_routes import smime_routes

MIGRATIONS = Path(__file__).parent / 'infrastructure' / 'migrations'
FETCH_EVERY_SECONDS = 60


def create_channels_module(
    context: ModuleContext,
    *,
    mailbox: Mailbox | None = None,
    outbox: Outbox | None = None,
    oauth: OAuthProviders | None = None,
) -> AppModule:
    """
    E-mail: several accounts per organization (IMAP in, SMTP out), each with its queue; signatures, salutations and
    auto replies per queue; filters for incoming mail; threading and loop protection; failed mails to process again.
    Mailboxes at Google and Microsoft 365 can be connected with OAuth instead of passwords.
    Tickets come and go through the tickets module's `TicketInbox` contract.
    """
    db, clock, ids, jobs = context.db, context.clock, context.ids, context.jobs
    engine = CryptographySmime()
    mailbox, outbox = mailbox or ImapMailbox(), outbox or SmtpOutbox(engine)
    accounts = PostgresAccountRepository(db)
    templates = PostgresTemplateRepository(db)
    queues = PostgresQueueChannelRepository(db)
    personal = PostgresPersonalRepository(db)
    filters = PostgresFilterRepository(db)
    failed = PostgresFailedEmailRepository(db)
    deliveries = PostgresDeliveryRepository(db)
    tickets = ContractTickets(context.contracts)
    names = ContractNames(context.contracts)
    connect_requests = PostgresConnectRequestRepository(db)
    oauth = oauth or HttpOAuthProviders(context.config, context.fetcher)
    vault = Vault(accounts, context.cipher, oauth, clock)
    certificates = PostgresCertificateRepository(db)
    smime = Smime(certificates, queues, engine, context.cipher, ids, clock)
    writer = Writer(queues, templates, personal, names)
    auto = AutoReplier(writer, vault, outbox, context.rate_limiter, ids, smime)
    process = ProcessEmailHandler(
        accounts, filters, failed, tickets, Nh3Cleaner(), auto, ids, clock, context.config.max_upload_bytes, smime
    )
    bus = (
        CommandBus()
        .register(CreateAccount, CreateAccountHandler(accounts, vault, ids, clock))
        .register(UpdateAccount, UpdateAccountHandler(accounts, vault, clock))
        .register(DeleteAccount, DeleteAccountHandler(accounts))
        .register(TestAccount, TestAccountHandler(accounts, vault, mailbox, outbox))
        .register(StartConnect, StartConnectHandler(accounts, connect_requests, oauth, clock))
        .register(FinishConnect, FinishConnectHandler(accounts, connect_requests, oauth, vault, ids, clock))
        .register(MailProviders, MailProvidersHandler(oauth))
        .register(FetchDue, FetchDueHandler(accounts, jobs))
        .register(FetchAccount, FetchAccountHandler(accounts, vault, mailbox, process, clock))
        .register(ProcessEmail, process)
        .register(RetryFailedEmail, RetryFailedEmailHandler(failed, process))
        .register(DeleteFailedEmail, DeleteFailedEmailHandler(failed))
        .register(QueueReply, QueueReplyHandler(deliveries, jobs, clock))
        .register(
            SendReply, SendReplyHandler(deliveries, queues, accounts, vault, outbox, tickets, jobs, ids, clock, smime)
        )
        .register(ResendReply, ResendReplyHandler(deliveries, jobs, clock))
        .register(SaveTemplate, SaveTemplateHandler(templates, ids, clock))
        .register(DeleteTemplate, DeleteTemplateHandler(templates))
        .register(SetQueueChannel, SetQueueChannelHandler(queues, accounts, templates, names))
        .register(SetPersonal, SetPersonalHandler(personal))
        .register(SaveFilter, SaveFilterHandler(filters, names, ids, clock))
        .register(DeleteFilter, DeleteFilterHandler(filters))
        .register(ReorderFilters, ReorderFiltersHandler(filters))
        .register(ForgetQueue, ForgetQueueHandler(queues))
        .register(ForgetMember, ForgetMemberHandler(personal))
        .register(ForgetTenant, ForgetTenantHandler(accounts))
        .register(ListAccounts, ListAccountsHandler(accounts))
        .register(ListTemplates, ListTemplatesHandler(templates))
        .register(ListQueueChannels, ListQueueChannelsHandler(queues))
        .register(GetPersonal, GetPersonalHandler(personal))
        .register(ListFilters, ListFiltersHandler(filters))
        .register(ListFailedEmails, ListFailedEmailsHandler(failed))
        .register(TicketDeliveries, TicketDeliveriesHandler(deliveries))
        .register(ReplyDraft, ReplyDraftHandler(writer))
        .register(AddCertificate, AddCertificateHandler(certificates, engine, context.cipher, ids, clock))
        .register(DeleteCertificate, DeleteCertificateHandler(certificates))
        .register(ListCertificates, ListCertificatesHandler(certificates))
    )

    async def message_added(event: MessageAdded) -> None:
        if event.kind == 'public' and event.direction == 'out':
            await bus.execute(QueueReply(event.tenant_id, event.ticket_id, event.message_id))

    async def queue_deleted(event: QueueDeleted) -> None:
        await bus.execute(ForgetQueue(event.tenant_id, event.queue_id))

    async def member_removed(event: MemberRemoved) -> None:
        await bus.execute(ForgetMember(event.tenant_id, event.user_id))

    async def user_deleted(event: UserDeleted) -> None:
        await bus.execute(ForgetMember(None, event.user_id))

    async def tenant_deleted(event: TenantDeleted) -> None:
        await bus.execute(ForgetTenant(event.tenant_id))

    context.events.subscribe(MessageAdded, message_added)
    context.events.subscribe(QueueDeleted, queue_deleted)
    context.events.subscribe(MemberRemoved, member_removed)
    context.events.subscribe(UserDeleted, user_deleted)
    context.events.subscribe(TenantDeleted, tenant_deleted)
    context.scheduler.every(FETCH_EVERY_SECONDS, 'channels.fetch_due', lambda: bus.execute(FetchDue()))

    async def fetch(tenant_id: str, account_id: str) -> None:
        await bus.execute(FetchAccount(tenant_id, account_id))

    async def send(tenant_id: str, message_id: str) -> None:
        await bus.execute(SendReply(tenant_id, message_id))

    return AppModule(
        name='channels',
        migrations=sql_migrations(MIGRATIONS),
        routers=[
            channel_routes(bus, jobs, context.config),
            oauth_callback_routes(bus, context.config),
            smime_routes(bus),
        ],
        tasks={FETCH_TASK: fetch, SEND_TASK: send},
    )
