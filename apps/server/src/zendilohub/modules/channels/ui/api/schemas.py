from datetime import datetime
from email import message_from_bytes, policy
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from zendilohub.core.http.ids import Id

from ...application.queries.channels import AccountView
from ...domain.models.account import Provider, Security
from ...domain.models.mail_filter import FilterField, MailFilter, Operator
from ...domain.models.records import Delivery, DeliveryStatus, FailedEmail
from ...domain.models.templates import PLACEHOLDERS, PersonalSettings, QueueChannel, TemplateKind, TextTemplate


class Request(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ServerRequest(Request):
    host: str = Field(max_length=253)
    port: int = Field(ge=1, le=65535)
    security: Security = 'ssl'
    username: str = Field(default='', max_length=254)
    password: str | None = Field(default=None, max_length=1000)
    """Leave out (or null) to keep the stored password."""


class AccountRequest(Request):
    name: str = Field(max_length=80)
    address: str = Field(max_length=254)
    display_name: str = Field(default='', max_length=80)
    """The sender's name in the customer's inbox, e.g. "Acme Support"."""
    queue_id: Id
    """Where new mails of this account go (filters can route elsewhere)."""
    imap: ServerRequest
    smtp: ServerRequest | None = None
    """Leave out (or null) for a mailbox for incoming mail only: no queue can send with it."""
    folder: str = Field(default='INBOX', max_length=200)
    active: bool = True


class ServerResponse(BaseModel):
    host: str
    port: int
    security: Security
    username: str
    has_password: bool


class AccountResponse(BaseModel):
    id: str
    name: str
    address: str
    display_name: str
    queue_id: str
    imap: ServerResponse
    smtp: ServerResponse | None
    """None: a mailbox for incoming mail only."""
    folder: str
    active: bool
    last_fetch_at: datetime | None
    last_error: str | None
    failing_since: datetime | None
    provider: Provider | None
    """Connected with OAuth at this provider (it fixes address and servers); None: logs in with passwords."""
    needs_reconnect: bool
    """The provider ended the connection: connect the mailbox again."""
    created_at: datetime

    @classmethod
    def of(cls, view: AccountView) -> AccountResponse:
        account, passwords = view.account, (view.has_imap_password, view.has_smtp_password)
        return cls(
            id=account.id,
            name=account.name,
            address=account.address,
            display_name=account.display_name,
            queue_id=account.queue_id,
            imap=ServerResponse(**vars(account.imap), has_password=passwords[0]),
            smtp=ServerResponse(**vars(account.smtp), has_password=passwords[1]) if account.smtp else None,
            folder=account.folder,
            active=account.active,
            last_fetch_at=account.last_fetch_at,
            last_error=account.last_error,
            failing_since=account.failing_since,
            provider=account.provider,
            needs_reconnect=account.needs_reconnect,
            created_at=account.created_at,
        )


class ConnectStartRequest(Request):
    provider: Provider
    account_id: Id | None = None
    """Connect this account (again); leave out for a new account in `queue_id`."""
    queue_id: Id | None = None
    name: str = Field(default='', max_length=80)
    """Of a new account; its address when left empty."""
    display_name: str = Field(default='', max_length=80)


class ConnectStartResponse(BaseModel):
    url: str
    """The provider's sign-in page; it sends the browser back to the app afterwards."""


class MailProvidersResponse(BaseModel):
    providers: list[Provider]
    """Where mailboxes can be connected with OAuth (the instance has app credentials for them)."""


class ProbeResponse(BaseModel):
    imap: str | None
    """None: logging in worked; else what went wrong."""
    smtp: str | None
    """Also None for a mailbox for incoming mail only (nothing to test)."""


class TemplateRequest(Request):
    kind: TemplateKind
    name: str = Field(max_length=80)
    body: str = Field(max_length=10_000)


class TemplateResponse(BaseModel):
    id: str
    kind: TemplateKind
    name: str
    body: str
    updated_at: datetime

    @classmethod
    def of(cls, template: TextTemplate) -> TemplateResponse:
        return cls(
            id=template.id, kind=template.kind, name=template.name, body=template.body, updated_at=template.updated_at
        )


class TemplatesResponse(BaseModel):
    templates: list[TemplateResponse]
    placeholders: list[str]

    @classmethod
    def of(cls, templates: list[TextTemplate]) -> TemplatesResponse:
        return cls(templates=[TemplateResponse.of(each) for each in templates], placeholders=list(PLACEHOLDERS))


class QueueChannelRequest(Request):
    account_id: Id | None = None
    """The account replies of the queue go out by; none: replies are not sent by e-mail."""
    signature_id: Id | None = None
    salutation_id: Id | None = None
    auto_reply: bool = False
    auto_reply_subject: str = Field(default='', max_length=250)
    auto_reply_body: str = Field(default='', max_length=10_000)


class QueueChannelResponse(BaseModel):
    queue_id: str
    account_id: str | None
    signature_id: str | None
    salutation_id: str | None
    auto_reply: bool
    auto_reply_subject: str
    auto_reply_body: str

    @classmethod
    def of(cls, settings: QueueChannel) -> QueueChannelResponse:
        return cls(**{key: value for key, value in vars(settings).items() if key != 'tenant_id'})


class PersonalRequest(Request):
    name: str = Field(default='', max_length=80)
    title: str = Field(default='', max_length=80)
    signature: str = Field(default='', max_length=10_000)


class PersonalResponse(BaseModel):
    name: str
    title: str
    signature: str

    @classmethod
    def of(cls, settings: PersonalSettings) -> PersonalResponse:
        return cls(name=settings.name, title=settings.title, signature=settings.signature)


class ConditionModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

    field: FilterField
    operator: Operator
    value: str = Field(max_length=500)
    header: str = Field(default='', max_length=80)


class ActionsModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

    queue_id: Id | None = None
    priority: Literal['low', 'normal', 'high', 'urgent'] | None = None
    tags: list[str] = Field(default_factory=list, max_length=10)
    ignore: bool = False


class FilterRequest(Request):
    name: str = Field(max_length=80)
    active: bool = True
    match: Literal['all', 'any'] = 'all'
    conditions: list[ConditionModel] = Field(min_length=1, max_length=10)
    actions: ActionsModel
    stop: bool = False
    account_id: Id | None = None
    """A rule of this mailbox (it runs after the filters for all mailboxes); null: a filter for all mailboxes."""


class FilterResponse(BaseModel):
    id: str
    account_id: str | None
    """The mailbox whose rule it is; null: for all mailboxes."""
    name: str
    position: int
    active: bool
    match: Literal['all', 'any']
    conditions: list[ConditionModel]
    actions: ActionsModel
    stop: bool

    @classmethod
    def of(cls, mail_filter: MailFilter) -> FilterResponse:
        actions = mail_filter.actions
        return cls(
            id=mail_filter.id,
            account_id=mail_filter.account_id,
            name=mail_filter.name,
            position=mail_filter.position,
            active=mail_filter.active,
            match=mail_filter.match,
            conditions=[ConditionModel(**vars(each)) for each in mail_filter.conditions],
            actions=ActionsModel(
                queue_id=actions.queue_id, priority=actions.priority, tags=list(actions.tags), ignore=actions.ignore
            ),
            stop=mail_filter.stop,
        )


class FilterOrderRequest(Request):
    filter_ids: list[Id] = Field(max_length=100)
    account_id: Id | None = None
    """Reorders the rules of this mailbox; null: the filters for all mailboxes."""


class FilterTestRequest(Request):
    raw: str = Field(max_length=1_000_000)
    """The e-mail with its headers, as the mail program shows its source."""
    account_id: Id | None = None
    """As if this mailbox received it: its rules run too, and its default queue is the fallback."""


class FilterTestResponse(BaseModel):
    matched: list[FilterResponse]
    """The filters that matched, in the order they ran."""
    stopped: bool
    """A matching filter ended the run (stop, or drop)."""
    ignore: bool
    """The e-mail would be dropped."""
    queue_id: str | None
    """The queue the filters chose; null: none did."""
    priority: str | None
    tags: list[str]
    default_queue_id: str | None
    """The mailbox's default queue."""
    final_queue_id: str | None
    """Where the e-mail would land; null: dropped, or no queue at all."""
    checked: int
    """How many active filters ran."""


class FailedEmailResponse(BaseModel):
    id: str
    account_id: str | None
    error: str
    received_at: datetime
    subject: str
    sender: str
    size: int

    @classmethod
    def of(cls, failed: FailedEmail) -> FailedEmailResponse:
        mail = message_from_bytes(failed.raw[:200_000], policy=policy.default)
        return cls(
            id=failed.id,
            account_id=failed.account_id,
            error=failed.error,
            received_at=failed.received_at,
            subject=str(mail.get('Subject', ''))[:250],
            sender=str(mail.get('From', ''))[:250],
            size=len(failed.raw),
        )


class RetryResponse(BaseModel):
    outcome: Literal['created', 'appended', 'ignored', 'duplicate', 'own', 'failed']


class DeliveryResponse(BaseModel):
    message_id: str
    status: DeliveryStatus
    error: str | None
    attempts: int
    updated_at: datetime

    @classmethod
    def of(cls, delivery: Delivery) -> DeliveryResponse:
        return cls(
            message_id=delivery.message_id,
            status=delivery.status,
            error=delivery.error,
            attempts=delivery.attempts,
            updated_at=delivery.updated_at,
        )


class DraftResponse(BaseModel):
    text: str
    """Salutation and signature of the queue, filled in; empty without them."""
