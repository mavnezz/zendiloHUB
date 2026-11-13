from collections.abc import Sequence
from dataclasses import dataclass

from zendilohub.core.bus.message import Command, Query
from zendilohub.core.domain.clock import Clock
from zendilohub.core.domain.id_generator import IdGenerator

from ...domain.models.text_module import (
    MODULES_MAX,
    InvalidTextModuleError,
    KeywordTakenError,
    TextModule,
    TextModuleNotFoundError,
)
from ...domain.ports.repositories import TextModuleRepository


@dataclass(frozen=True, kw_only=True)
class SaveTextModule(Command[TextModule]):
    tenant_id: str
    name: str
    keyword: str
    body: str
    queue_ids: tuple[str, ...] = ()
    module_id: str | None = None


class SaveTextModuleHandler:
    def __init__(self, modules: TextModuleRepository, ids: IdGenerator, clock: Clock) -> None:
        self._modules = modules
        self._ids = ids
        self._clock = clock

    async def handle(self, command: SaveTextModule) -> TextModule:
        existing = list(await self._modules.of_tenant(command.tenant_id))
        now = self._clock.now()
        if command.module_id is None:
            if len(existing) >= MODULES_MAX:
                raise InvalidTextModuleError('limit')
            module = TextModule(
                id=self._ids.new_id(),
                tenant_id=command.tenant_id,
                name=command.name,
                keyword=command.keyword,
                body=command.body,
                queue_ids=command.queue_ids,
                created_at=now,
                updated_at=now,
            )
        else:
            found = next((each for each in existing if each.id == command.module_id), None)
            if found is None:
                raise TextModuleNotFoundError()
            module = found
            module.name, module.keyword, module.body = command.name, command.keyword, command.body
            module.queue_ids, module.updated_at = command.queue_ids, now
        module.check()
        if any(each.keyword == module.keyword and each.id != module.id for each in existing):
            raise KeywordTakenError()
        await self._modules.save(module)
        return module


@dataclass(frozen=True, kw_only=True)
class DeleteTextModule(Command[TextModule]):
    tenant_id: str
    module_id: str


class DeleteTextModuleHandler:
    def __init__(self, modules: TextModuleRepository) -> None:
        self._modules = modules

    async def handle(self, command: DeleteTextModule) -> TextModule:
        found = await self._modules.find(command.tenant_id, command.module_id)
        if found is None:
            raise TextModuleNotFoundError()
        await self._modules.delete(command.tenant_id, found.id)
        return found


@dataclass(frozen=True, kw_only=True)
class ListTextModules(Query[Sequence[TextModule]]):
    tenant_id: str
    queue_id: str | None = None
    """Only those for this queue (and those for every queue)."""


class ListTextModulesHandler:
    def __init__(self, modules: TextModuleRepository) -> None:
        self._modules = modules

    async def handle(self, query: ListTextModules) -> Sequence[TextModule]:
        return [each for each in await self._modules.of_tenant(query.tenant_id) if each.fits(query.queue_id)]


@dataclass(frozen=True)
class ForgetQueue(Command[None]):
    tenant_id: str
    queue_id: str


class ForgetQueueHandler:
    def __init__(self, modules: TextModuleRepository) -> None:
        self._modules = modules

    async def handle(self, command: ForgetQueue) -> None:
        await self._modules.forget_queue(command.tenant_id, command.queue_id)


@dataclass(frozen=True)
class ForgetTenant(Command[None]):
    tenant_id: str


class ForgetTenantHandler:
    def __init__(self, modules: TextModuleRepository) -> None:
        self._modules = modules

    async def handle(self, command: ForgetTenant) -> None:
        await self._modules.forget_tenant(command.tenant_id)
