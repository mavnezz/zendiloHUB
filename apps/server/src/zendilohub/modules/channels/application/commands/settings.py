from dataclasses import dataclass, replace

from zendilohub.core.bus.message import Command, Query
from zendilohub.core.domain.clock import Clock
from zendilohub.core.domain.id_generator import IdGenerator

from ...domain.exceptions import (
    AccountNotFoundError,
    FilterNotFoundError,
    InvalidFilterError,
    InvalidQueueSettingsError,
    TemplateInUseError,
    TemplateNotFoundError,
)
from ...domain.models.email import parse_email
from ...domain.models.mail_filter import FILTERS_MAX, Condition, FilterActions, MailFilter, in_order, route
from ...domain.models.templates import PersonalSettings, QueueChannel, TemplateKind, TextTemplate
from ...domain.ports.repositories import (
    AccountRepository,
    FilterRepository,
    PersonalRepository,
    QueueChannelRepository,
    TemplateRepository,
)
from ...domain.ports.services import Names


@dataclass(frozen=True, kw_only=True)
class SaveTemplate(Command[TextTemplate]):
    """Creates (without `template_id`) or changes a signature or salutation."""

    tenant_id: str
    kind: TemplateKind
    name: str
    body: str
    template_id: str | None = None


class SaveTemplateHandler:
    def __init__(self, templates: TemplateRepository, ids: IdGenerator, clock: Clock) -> None:
        self._templates = templates
        self._ids = ids
        self._clock = clock

    async def handle(self, command: SaveTemplate) -> TextTemplate:
        now = self._clock.now()
        if command.template_id is None:
            template = TextTemplate.create(
                id=self._ids.new_id(),
                tenant_id=command.tenant_id,
                kind=command.kind,
                name=command.name,
                body=command.body,
                now=now,
            )
        else:
            found = await self._templates.find(command.tenant_id, command.template_id)
            if found is None or found.kind != command.kind:
                raise TemplateNotFoundError()
            template = found
            template.change(name=command.name, body=command.body, now=now)
        await self._templates.save(template)
        return template


@dataclass(frozen=True, kw_only=True)
class DeleteTemplate(Command[TextTemplate]):
    tenant_id: str
    template_id: str


class DeleteTemplateHandler:
    def __init__(self, templates: TemplateRepository) -> None:
        self._templates = templates

    async def handle(self, command: DeleteTemplate) -> TextTemplate:
        template = await self._templates.find(command.tenant_id, command.template_id)
        if template is None:
            raise TemplateNotFoundError()
        if await self._templates.in_use(command.tenant_id, template.id):
            raise TemplateInUseError()
        await self._templates.delete(command.tenant_id, template.id)
        return template


@dataclass(frozen=True)
class SetQueueChannel(Command[QueueChannel]):
    settings: QueueChannel


class SetQueueChannelHandler:
    def __init__(
        self,
        queues: QueueChannelRepository,
        accounts: AccountRepository,
        templates: TemplateRepository,
        names: Names,
    ) -> None:
        self._queues = queues
        self._accounts = accounts
        self._templates = templates
        self._names = names

    async def handle(self, command: SetQueueChannel) -> QueueChannel:
        settings = command.settings
        tenant_id = settings.tenant_id
        if await self._names.queue(tenant_id, settings.queue_id) is None:
            raise InvalidQueueSettingsError('queue_id')
        account = await self._accounts.find(tenant_id, settings.account_id) if settings.account_id else None
        if settings.account_id and account is None:
            raise AccountNotFoundError()
        if account is not None and not account.sends:
            # A mailbox for incoming mail only has no server to send with.
            raise InvalidQueueSettingsError('account_id')
        for template_id, kind in ((settings.signature_id, 'signature'), (settings.salutation_id, 'salutation')):
            template = await self._templates.find(tenant_id, template_id) if template_id else None
            if template_id and (template is None or template.kind != kind):
                raise TemplateNotFoundError()
        settings.check()
        await self._queues.save(settings)
        return settings


@dataclass(frozen=True, kw_only=True)
class SetPersonal(Command[PersonalSettings]):
    tenant_id: str
    user_id: str
    name: str
    title: str
    signature: str


class SetPersonalHandler:
    def __init__(self, personal: PersonalRepository) -> None:
        self._personal = personal

    async def handle(self, command: SetPersonal) -> PersonalSettings:
        settings = PersonalSettings(
            tenant_id=command.tenant_id, user_id=command.user_id, name='', title='', signature=''
        )
        settings.change(name=command.name, title=command.title, signature=command.signature)
        await self._personal.save(settings)
        return settings


@dataclass(frozen=True, kw_only=True)
class FilterFields:
    name: str
    active: bool
    match: str
    conditions: tuple[Condition, ...]
    actions: FilterActions
    stop: bool
    account_id: str | None = None
    """A rule of this mailbox; None: a filter for all mailboxes."""


@dataclass(frozen=True, kw_only=True)
class SaveFilter(Command[MailFilter]):
    tenant_id: str
    fields: FilterFields
    filter_id: str | None = None


class SaveFilterHandler:
    def __init__(
        self, filters: FilterRepository, accounts: AccountRepository, names: Names, ids: IdGenerator, clock: Clock
    ) -> None:
        self._filters = filters
        self._accounts = accounts
        self._names = names
        self._ids = ids
        self._clock = clock

    async def handle(self, command: SaveFilter) -> MailFilter:
        fields, now = command.fields, self._clock.now()
        if fields.match not in ('all', 'any'):
            raise InvalidFilterError('match')
        if fields.account_id and await self._accounts.find(command.tenant_id, fields.account_id) is None:
            raise InvalidFilterError('account_id')
        existing = list(await self._filters.of_tenant(command.tenant_id))
        # Each scope (all mailboxes, or one mailbox) has its own order; a filter joins the end of its scope.
        last = max((each.position for each in existing if each.account_id == fields.account_id), default=0)
        if command.filter_id is None:
            if len(existing) >= FILTERS_MAX:
                raise InvalidFilterError('limit')
            mail_filter = MailFilter(
                id=self._ids.new_id(),
                tenant_id=command.tenant_id,
                account_id=fields.account_id,
                name=fields.name,
                position=last + 1,
                active=fields.active,
                match='all' if fields.match == 'all' else 'any',
                conditions=fields.conditions,
                actions=fields.actions,
                stop=fields.stop,
                created_at=now,
                updated_at=now,
            )
        else:
            found = next((each for each in existing if each.id == command.filter_id), None)
            if found is None:
                raise FilterNotFoundError()
            mail_filter = replace(
                found,
                account_id=fields.account_id,
                position=found.position if found.account_id == fields.account_id else last + 1,
                name=fields.name,
                active=fields.active,
                match='all' if fields.match == 'all' else 'any',
                conditions=fields.conditions,
                actions=fields.actions,
                stop=fields.stop,
                updated_at=now,
            )
        mail_filter.check()
        queue_id = mail_filter.actions.queue_id
        if queue_id and await self._names.queue(command.tenant_id, queue_id) is None:
            raise InvalidFilterError('actions.queue_id')
        await self._filters.save(mail_filter)
        return mail_filter


@dataclass(frozen=True, kw_only=True)
class DeleteFilter(Command[MailFilter]):
    tenant_id: str
    filter_id: str


class DeleteFilterHandler:
    def __init__(self, filters: FilterRepository) -> None:
        self._filters = filters

    async def handle(self, command: DeleteFilter) -> MailFilter:
        found = await self._filters.find(command.tenant_id, command.filter_id)
        if found is None:
            raise FilterNotFoundError()
        await self._filters.delete(command.tenant_id, found.id)
        return found


@dataclass(frozen=True, kw_only=True)
class ReorderFilters(Command[None]):
    """The filters of one scope in this order (ids); filters not named keep their place after them."""

    tenant_id: str
    filter_ids: tuple[str, ...]
    account_id: str | None = None
    """The rules of this mailbox; None: the filters for all mailboxes."""


class ReorderFiltersHandler:
    def __init__(self, filters: FilterRepository) -> None:
        self._filters = filters

    async def handle(self, command: ReorderFilters) -> None:
        existing = [
            each for each in await self._filters.of_tenant(command.tenant_id) if each.account_id == command.account_id
        ]
        existing.sort(key=lambda each: each.position)
        known = {each.id: each for each in existing}
        if any(filter_id not in known for filter_id in command.filter_ids):
            raise FilterNotFoundError()
        ordered = [known[filter_id] for filter_id in dict.fromkeys(command.filter_ids)]
        ordered += [each for each in existing if each.id not in command.filter_ids]
        for position, each in enumerate(ordered, start=1):
            if each.position != position:
                each.position = position
                await self._filters.save(each)


@dataclass(frozen=True)
class ForgetQueue(Command[None]):
    tenant_id: str
    queue_id: str


class ForgetQueueHandler:
    def __init__(self, queues: QueueChannelRepository) -> None:
        self._queues = queues

    async def handle(self, command: ForgetQueue) -> None:
        await self._queues.delete(command.tenant_id, command.queue_id)


@dataclass(frozen=True)
class ForgetMember(Command[None]):
    tenant_id: str | None
    user_id: str


class ForgetMemberHandler:
    def __init__(self, personal: PersonalRepository) -> None:
        self._personal = personal

    async def handle(self, command: ForgetMember) -> None:
        await self._personal.forget(command.tenant_id, command.user_id)


@dataclass(frozen=True)
class ForgetTenant(Command[None]):
    tenant_id: str


class ForgetTenantHandler:
    def __init__(self, accounts: AccountRepository) -> None:
        self._accounts = accounts

    async def handle(self, command: ForgetTenant) -> None:
        await self._accounts.forget_tenant(command.tenant_id)


@dataclass(frozen=True, kw_only=True)
class FilterTrace:
    """Where a test e-mail would go: the filters that matched in order, what they decided, and the queue."""

    matched: tuple[MailFilter, ...]
    stopped: bool
    ignore: bool
    queue_id: str | None
    """What the filters chose; None: none chose a queue."""
    priority: str | None
    tags: tuple[str, ...]
    default_queue_id: str | None
    """The mailbox's default queue."""
    final_queue_id: str | None
    """Where the e-mail lands (None: dropped, or no mailbox and no filter chose a queue)."""
    checked: int
    """How many filters ran for this mailbox."""


@dataclass(frozen=True, kw_only=True)
class TestFilters(Query[FilterTrace]):
    """Runs the filters for all mailboxes, then the mailbox's rules, on a pasted e-mail; changes nothing."""

    tenant_id: str
    raw: bytes
    account_id: str | None = None


class TestFiltersHandler:
    def __init__(self, filters: FilterRepository, accounts: AccountRepository) -> None:
        self._filters = filters
        self._accounts = accounts

    async def handle(self, query: TestFilters) -> FilterTrace:
        account = await self._accounts.find(query.tenant_id, query.account_id) if query.account_id else None
        if query.account_id and account is None:
            raise AccountNotFoundError()
        mail = parse_email(query.raw)
        filters = list(await self._filters.of_tenant(query.tenant_id))
        routing = route(filters, mail, query.account_id)
        by_id = {each.id: each for each in filters}
        default = account.queue_id if account else None
        return FilterTrace(
            matched=tuple(by_id[each] for each in routing.matched),
            stopped=routing.stopped,
            ignore=routing.ignore,
            queue_id=routing.queue_id,
            priority=routing.priority,
            tags=routing.tags,
            default_queue_id=default,
            final_queue_id=None if routing.ignore else routing.queue_id or default,
            checked=len([each for each in in_order(filters, query.account_id) if each.active]),
        )
