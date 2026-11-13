from collections.abc import Sequence
from dataclasses import dataclass

from zendilohub.core.bus.message import Query

from ...domain.models.account import EmailAccount
from ...domain.models.mail_filter import MailFilter
from ...domain.models.records import Delivery, FailedEmail
from ...domain.models.templates import PersonalSettings, QueueChannel, TemplateKind, TextTemplate
from ...domain.ports.repositories import (
    AccountRepository,
    DeliveryRepository,
    FailedEmailRepository,
    FilterRepository,
    PersonalRepository,
    QueueChannelRepository,
    TemplateRepository,
)
from ..services.writer import Context, Writer


@dataclass(frozen=True)
class AccountView:
    account: EmailAccount
    has_imap_password: bool
    has_smtp_password: bool


@dataclass(frozen=True)
class ListAccounts(Query[Sequence[AccountView]]):
    tenant_id: str
    account_id: str | None = None


class ListAccountsHandler:
    def __init__(self, accounts: AccountRepository) -> None:
        self._accounts = accounts

    async def handle(self, query: ListAccounts) -> Sequence[AccountView]:
        listed = await self._accounts.of_tenant(query.tenant_id)
        return [
            AccountView(
                each,
                await self._accounts.password(each.id, 'imap') is not None,
                await self._accounts.password(each.id, 'smtp') is not None,
            )
            for each in listed
            if query.account_id is None or each.id == query.account_id
        ]


@dataclass(frozen=True)
class ListTemplates(Query[Sequence[TextTemplate]]):
    tenant_id: str
    kind: TemplateKind | None = None


class ListTemplatesHandler:
    def __init__(self, templates: TemplateRepository) -> None:
        self._templates = templates

    async def handle(self, query: ListTemplates) -> Sequence[TextTemplate]:
        return await self._templates.of_tenant(query.tenant_id, query.kind)


@dataclass(frozen=True)
class ListQueueChannels(Query[Sequence[QueueChannel]]):
    tenant_id: str


class ListQueueChannelsHandler:
    def __init__(self, queues: QueueChannelRepository) -> None:
        self._queues = queues

    async def handle(self, query: ListQueueChannels) -> Sequence[QueueChannel]:
        return await self._queues.of_tenant(query.tenant_id)


@dataclass(frozen=True)
class GetPersonal(Query[PersonalSettings]):
    tenant_id: str
    user_id: str


class GetPersonalHandler:
    def __init__(self, personal: PersonalRepository) -> None:
        self._personal = personal

    async def handle(self, query: GetPersonal) -> PersonalSettings:
        found = await self._personal.find(query.tenant_id, query.user_id)
        return found or PersonalSettings(
            tenant_id=query.tenant_id, user_id=query.user_id, name='', title='', signature=''
        )


@dataclass(frozen=True)
class ListFilters(Query[Sequence[MailFilter]]):
    tenant_id: str


class ListFiltersHandler:
    def __init__(self, filters: FilterRepository) -> None:
        self._filters = filters

    async def handle(self, query: ListFilters) -> Sequence[MailFilter]:
        return await self._filters.of_tenant(query.tenant_id)


@dataclass(frozen=True)
class ListFailedEmails(Query[Sequence[FailedEmail]]):
    tenant_id: str


class ListFailedEmailsHandler:
    def __init__(self, failed: FailedEmailRepository) -> None:
        self._failed = failed

    async def handle(self, query: ListFailedEmails) -> Sequence[FailedEmail]:
        return await self._failed.of_tenant(query.tenant_id)


@dataclass(frozen=True)
class TicketDeliveries(Query[Sequence[Delivery]]):
    tenant_id: str
    ticket_id: str


class TicketDeliveriesHandler:
    def __init__(self, deliveries: DeliveryRepository) -> None:
        self._deliveries = deliveries

    async def handle(self, query: TicketDeliveries) -> Sequence[Delivery]:
        return await self._deliveries.of_ticket(query.tenant_id, query.ticket_id)


@dataclass(frozen=True)
class ReplyDraft(Query[str]):
    context: Context


class ReplyDraftHandler:
    def __init__(self, writer: Writer) -> None:
        self._writer = writer

    async def handle(self, query: ReplyDraft) -> str:
        return await self._writer.reply_draft(query.context)
