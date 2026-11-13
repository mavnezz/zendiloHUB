from typing import Annotated

from fastapi import APIRouter, Request, Response

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.http.access import CurrentMember, Member, member_with
from zendilohub.core.http.audit import audited, note_audit
from zendilohub.core.http.ids import Id

from ...application.commands.rules import DeleteRule, ListRules, RuleFields, SaveRule
from ...domain.models.rules import Actions, RuleCondition, RuleKind, Schedule
from .schemas import RuleRequest, RuleResponse

Admin = Annotated[Member, member_with('automation.manage')]

PATHS: dict[RuleKind, str] = {'macro': 'macros', 'trigger': 'triggers', 'schedule': 'scheduled-jobs'}


def _fields(kind: RuleKind, body: RuleRequest) -> RuleFields:
    actions = body.actions
    schedule = body.schedule
    return RuleFields(
        kind=kind,
        name=body.name,
        active=body.active,
        actions=Actions(
            **actions.model_dump(exclude={'add_tags', 'remove_tags'}),
            add_tags=tuple(tag.strip().lower() for tag in actions.add_tags if tag.strip()),
            remove_tags=tuple(tag.strip().lower() for tag in actions.remove_tags if tag.strip()),
        ),
        event=body.event,
        conditions=tuple(RuleCondition(**each.model_dump()) for each in body.conditions),
        schedule=Schedule(
            states=tuple(schedule.states),
            queue_ids=tuple(schedule.queue_ids),
            priorities=tuple(schedule.priorities),
            tags=tuple(tag.strip().lower() for tag in schedule.tags if tag.strip()),
            owner=schedule.owner,
            idle_hours=schedule.idle_hours,
            age_hours=schedule.age_hours,
            pending_passed=schedule.pending_passed,
        )
        if schedule
        else None,
    )


def automation_routes(bus: CommandBus) -> APIRouter:
    """
    Macros (every member sees them, to apply them in tickets), triggers and scheduled jobs (administrators set them
    up; they act on tickets whatever anyone's rights).
    """
    router = APIRouter(prefix='/tenants/{tenant_id}', tags=['automation'])

    @router.get('/macros')
    async def macros(member: CurrentMember) -> list[RuleResponse]:
        return [RuleResponse.of(each) for each in await bus.query(ListRules(tenant_id=member.tenant_id, kind='macro'))]

    for kind, path in PATHS.items():
        _add_routes(router, bus, kind, path)
    return router


def _add_routes(router: APIRouter, bus: CommandBus, kind: RuleKind, path: str) -> None:
    if kind != 'macro':

        @router.get(f'/{path}', name=f'list_{kind}s')
        async def listed(member: Admin) -> list[RuleResponse]:
            return [RuleResponse.of(each) for each in await bus.query(ListRules(tenant_id=member.tenant_id, kind=kind))]

    @router.post(f'/{path}', status_code=201, name=f'create_{kind}', dependencies=[audited(f'{kind}.created')])
    async def create(body: RuleRequest, request: Request, member: Admin) -> RuleResponse:
        rule = await bus.execute(SaveRule(tenant_id=member.tenant_id, fields=_fields(kind, body)))
        note_audit(request, target=rule.name)
        return RuleResponse.of(rule)

    @router.patch(f'/{path}/{{rule_id}}', name=f'update_{kind}', dependencies=[audited(f'{kind}.updated')])
    async def update(rule_id: Id, body: RuleRequest, request: Request, member: Admin) -> RuleResponse:
        rule = await bus.execute(SaveRule(tenant_id=member.tenant_id, fields=_fields(kind, body), rule_id=rule_id))
        note_audit(request, target=rule.name)
        return RuleResponse.of(rule)

    @router.delete(
        f'/{path}/{{rule_id}}',
        status_code=204,
        response_class=Response,
        name=f'delete_{kind}',
        dependencies=[audited(f'{kind}.deleted')],
    )
    async def delete(rule_id: Id, request: Request, member: Admin) -> None:
        rule = await bus.execute(DeleteRule(tenant_id=member.tenant_id, rule_id=rule_id))
        note_audit(request, target=rule.name)
