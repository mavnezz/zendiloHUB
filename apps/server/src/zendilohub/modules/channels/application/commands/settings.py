from dataclasses import dataclass, replace

from zendilohub.core.bus.message import Command
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
from ...domain.models.mail_filter import FILTERS_MAX, Condition, FilterActions, MailFilter
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
        if settings.account_id and await self._accounts.find(tenant_id, settings.account_id) is None:
            raise AccountNotFoundError()
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


@dataclass(frozen=True, kw_only=True)
class SaveFilter(Command[MailFilter]):
    tenant_id: str
    fields: FilterFields
    filter_id: str | None = None


class SaveFilterHandler:
    def __init__(self, filters: FilterRepository, names: Names, ids: IdGenerator, clock: Clock) -> None:
        self._filters = filters
        self._names = names
        self._ids = ids
        self._clock = clock

    async def handle(self, command: SaveFilter) -> MailFilter:
        fields, now = command.fields, self._clock.now()
        if fields.match not in ('all', 'any'):
            raise InvalidFilterError('match')
        existing = list(await self._filters.of_tenant(command.tenant_id))
        if command.filter_id is None:
            if len(existing) >= FILTERS_MAX:
                raise InvalidFilterError('limit')
            mail_filter = MailFilter(
                id=self._ids.new_id(),
                tenant_id=command.tenant_id,
                name=fields.name,
                position=max((each.position for each in existing), default=0) + 1,
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
    """The filters in this order (ids); filters not named keep their place after them."""

    tenant_id: str
    filter_ids: tuple[str, ...]


class ReorderFiltersHandler:
    def __init__(self, filters: FilterRepository) -> None:
        self._filters = filters

    async def handle(self, command: ReorderFilters) -> None:
        existing = list(await self._filters.of_tenant(command.tenant_id))
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
