from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.http.access import CurrentMember, Member, member_with
from zendilohub.core.http.audit import audited, note_audit
from zendilohub.core.http.ids import Id

from ...application.commands.text_modules import DeleteTextModule, ListTextModules, SaveTextModule
from ...domain.models.text_module import TextModule

Editor = Annotated[Member, member_with('knowledge.manage')]


class TextModuleRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: str = Field(max_length=80)
    keyword: str = Field(max_length=30)
    """Typed as `::keyword` in the editor."""
    body: str = Field(max_length=20_000)
    queue_ids: list[Id] = Field(default_factory=list, max_length=200)
    """Only in these queues; empty: in every queue."""


class TextModuleResponse(BaseModel):
    id: str
    name: str
    keyword: str
    body: str
    queue_ids: list[str]
    updated_at: datetime

    @classmethod
    def of(cls, module: TextModule) -> TextModuleResponse:
        return cls(
            id=module.id,
            name=module.name,
            keyword=module.keyword,
            body=module.body,
            queue_ids=list(module.queue_ids),
            updated_at=module.updated_at,
        )


def knowledge_routes(bus: CommandBus) -> APIRouter:
    router = APIRouter(prefix='/tenants/{tenant_id}', tags=['knowledge'])

    @router.get('/text-modules')
    async def text_modules(
        member: CurrentMember, queue_id: Annotated[Id | None, Query()] = None
    ) -> list[TextModuleResponse]:
        """Every member uses them; with `queue_id` only those for that queue."""
        listed = await bus.query(ListTextModules(tenant_id=member.tenant_id, queue_id=queue_id))
        return [TextModuleResponse.of(each) for each in listed]

    @router.post('/text-modules', status_code=201, dependencies=[audited('text_module.created')])
    async def create(body: TextModuleRequest, request: Request, member: Editor) -> TextModuleResponse:
        module = await bus.execute(
            SaveTextModule(
                tenant_id=member.tenant_id,
                name=body.name,
                keyword=body.keyword,
                body=body.body,
                queue_ids=tuple(body.queue_ids),
            )
        )
        note_audit(request, target=module.keyword)
        return TextModuleResponse.of(module)

    @router.patch('/text-modules/{module_id}', dependencies=[audited('text_module.updated')])
    async def update(module_id: Id, body: TextModuleRequest, request: Request, member: Editor) -> TextModuleResponse:
        module = await bus.execute(
            SaveTextModule(
                tenant_id=member.tenant_id,
                name=body.name,
                keyword=body.keyword,
                body=body.body,
                queue_ids=tuple(body.queue_ids),
                module_id=module_id,
            )
        )
        note_audit(request, target=module.keyword)
        return TextModuleResponse.of(module)

    @router.delete(
        '/text-modules/{module_id}',
        status_code=204,
        response_class=Response,
        dependencies=[audited('text_module.deleted')],
    )
    async def delete(module_id: Id, request: Request, member: Editor) -> None:
        module = await bus.execute(DeleteTextModule(tenant_id=member.tenant_id, module_id=module_id))
        note_audit(request, target=module.keyword)

    return router
