import logging
from collections.abc import Sequence
from dataclasses import dataclass

from zendilohub.core.bus.message import Command, Query
from zendilohub.core.domain.clock import Clock
from zendilohub.core.domain.id_generator import IdGenerator
from zendilohub.core.domain.transaction import TransactionManager

from ...domain.exceptions import InvalidRuleError, RuleNotFoundError
from ...domain.models.rules import RULES_MAX, Actions, Rule, RuleCondition, RuleKind, Schedule, TriggerEvent
from ...domain.ports.repositories import RuleRepository, Tickets
from ..services.alerts import AlertMailer

logger = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class RuleFields:
    kind: RuleKind
    name: str
    active: bool
    actions: Actions
    event: TriggerEvent | None = None
    conditions: tuple[RuleCondition, ...] = ()
    schedule: Schedule | None = None


@dataclass(frozen=True, kw_only=True)
class SaveRule(Command[Rule]):
    tenant_id: str
    fields: RuleFields
    rule_id: str | None = None


class SaveRuleHandler:
    def __init__(self, rules: RuleRepository, ids: IdGenerator, clock: Clock) -> None:
        self._rules = rules
        self._ids = ids
        self._clock = clock

    async def handle(self, command: SaveRule) -> Rule:
        fields, now = command.fields, self._clock.now()
        existing = list(await self._rules.of_tenant(command.tenant_id, fields.kind))
        if command.rule_id is None:
            if len(existing) >= RULES_MAX:
                raise InvalidRuleError('limit')
            rule = Rule(
                id=self._ids.new_id(),
                tenant_id=command.tenant_id,
                kind=fields.kind,
                name=fields.name,
                active=fields.active,
                position=max((each.position for each in existing), default=0) + 1,
                actions=fields.actions,
                event=fields.event,
                conditions=fields.conditions,
                schedule=fields.schedule,
                created_at=now,
                updated_at=now,
            )
        else:
            found = next((each for each in existing if each.id == command.rule_id), None)
            if found is None:
                raise RuleNotFoundError()
            rule = found
            rule.name, rule.active, rule.actions = fields.name, fields.active, fields.actions
            rule.event, rule.conditions, rule.schedule = fields.event, fields.conditions, fields.schedule
            rule.updated_at = now
        rule.check()
        await self._rules.save(rule)
        return rule


@dataclass(frozen=True, kw_only=True)
class DeleteRule(Command[Rule]):
    tenant_id: str
    rule_id: str


class DeleteRuleHandler:
    def __init__(self, rules: RuleRepository) -> None:
        self._rules = rules

    async def handle(self, command: DeleteRule) -> Rule:
        found = await self._rules.find(command.tenant_id, command.rule_id)
        if found is None:
            raise RuleNotFoundError()
        await self._rules.delete(command.tenant_id, found.id)
        return found


@dataclass(frozen=True, kw_only=True)
class ListRules(Query[Sequence[Rule]]):
    tenant_id: str
    kind: RuleKind


class ListRulesHandler:
    def __init__(self, rules: RuleRepository) -> None:
        self._rules = rules

    async def handle(self, query: ListRules) -> Sequence[Rule]:
        return await self._rules.of_tenant(query.tenant_id, query.kind)


@dataclass(frozen=True, kw_only=True)
class RunTriggers(Command[int]):
    """Something happened to a ticket: the organization's triggers for it run, in order; returns how many acted."""

    tenant_id: str
    ticket_id: str
    event: TriggerEvent


class RunTriggersHandler:
    def __init__(
        self, rules: RuleRepository, tickets: Tickets, transactions: TransactionManager, alerts: AlertMailer
    ) -> None:
        self._rules = rules
        self._tickets = tickets
        self._transactions = transactions
        self._alerts = alerts

    async def handle(self, command: RunTriggers) -> int:
        triggers = [each for each in await self._rules.of_tenant(command.tenant_id, 'trigger') if each.active]
        acted = 0
        for trigger in triggers:
            facts = await self._tickets.facts(command.tenant_id, command.ticket_id)
            if facts is None:
                break
            if not trigger.applies_to(command.event, facts):
                continue
            try:
                # A savepoint: a failing trigger must not undo what started it (e.g. an incoming e-mail).
                async with self._transactions.transaction():
                    changed = await self._tickets.apply(
                        command.tenant_id, facts.id, trigger.actions.changes(), by=f'Trigger: {trigger.name}'
                    )
                alerted = await self._alert(trigger, command.tenant_id, facts.id)
                acted += int(changed or alerted > 0)
            except Exception:
                logger.exception('A trigger failed', extra={'trigger': trigger.id})
        return acted

    async def _alert(self, rule: Rule, tenant_id: str, ticket_id: str) -> int:
        if not rule.actions.notify_emails:
            return 0
        # As the ticket is now: the rule may just have moved it or raised its priority.
        facts = await self._tickets.facts(tenant_id, ticket_id)
        return await self._alerts.send(rule, facts) if facts else 0


@dataclass(frozen=True)
class RunSchedules(Command[int]):
    """Every active scheduled job of every organization on the tickets that fit it; returns the tickets changed."""


class RunSchedulesHandler:
    def __init__(
        self,
        rules: RuleRepository,
        tickets: Tickets,
        transactions: TransactionManager,
        clock: Clock,
    ) -> None:
        self._rules = rules
        self._tickets = tickets
        self._transactions = transactions
        self._clock = clock

    async def handle(self, command: RunSchedules) -> int:
        changed = 0
        for rule in await self._rules.active_schedules():
            assert rule.schedule is not None
            now = self._clock.now()
            for ticket_id in await self._tickets.find(rule.tenant_id, rule.schedule.criteria(now)):
                try:
                    async with self._transactions.transaction():
                        changed += int(
                            await self._tickets.apply(
                                rule.tenant_id, ticket_id, rule.actions.changes(), by=f'Job: {rule.name}'
                            )
                        )
                except Exception:
                    logger.exception('A scheduled job failed', extra={'job': rule.id})
            rule.last_run_at = now
            await self._rules.save(rule)
        return changed


@dataclass(frozen=True)
class ForgetTenant(Command[None]):
    tenant_id: str


class ForgetTenantHandler:
    def __init__(self, rules: RuleRepository) -> None:
        self._rules = rules

    async def handle(self, command: ForgetTenant) -> None:
        await self._rules.forget_tenant(command.tenant_id)
