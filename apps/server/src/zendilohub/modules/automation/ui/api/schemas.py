from dataclasses import asdict
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from zendilohub.core.http.ids import Id

from ...domain.models.rules import ConditionField, ConditionOperator, Rule, RuleKind, TriggerEvent


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ActionsModel(Strict):
    state: Literal['new', 'open', 'pending_reminder', 'pending_close', 'closed'] | None = None
    pending_hours: int | None = Field(default=None, ge=1, le=24 * 365)
    """For a pending state: until this many hours from when the rule runs (default 24)."""
    priority: Literal['low', 'normal', 'high', 'urgent'] | None = None
    queue_id: Id | None = None
    owner_id: Id | None = None
    owner_me: bool = False
    """Macros: the ticket goes to whoever applies the macro."""
    unassign: bool = False
    add_tags: list[str] = Field(default_factory=list, max_length=20)
    remove_tags: list[str] = Field(default_factory=list, max_length=20)
    note: str = Field(default='', max_length=10_000)
    reply: str = Field(default='', max_length=10_000)
    """Triggers and jobs: a message to the customer (sent by e-mail when the queue has an account)."""


class ConditionModel(Strict):
    field: ConditionField
    operator: ConditionOperator
    value: str = Field(default='', max_length=500)


class ScheduleModel(Strict):
    states: list[Literal['new', 'open', 'pending_reminder', 'pending_close']] = Field(default_factory=list)
    queue_ids: list[Id] = Field(default_factory=list, max_length=200)
    priorities: list[Literal['low', 'normal', 'high', 'urgent']] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list, max_length=20)
    owner: Literal['any', 'none', 'set'] = 'any'
    idle_hours: int | None = Field(default=None, ge=1, le=24 * 365)
    age_hours: int | None = Field(default=None, ge=1, le=24 * 365)
    pending_passed: bool = False


class RuleRequest(Strict):
    name: str = Field(max_length=80)
    active: bool = True
    actions: ActionsModel
    event: TriggerEvent | None = None
    """Triggers: when they run (`created`, `customer_replied`, `updated`)."""
    conditions: list[ConditionModel] = Field(default_factory=list, max_length=10)
    """Triggers: all must hold."""
    schedule: ScheduleModel | None = None
    """Scheduled jobs: which tickets they take."""


class RuleResponse(BaseModel):
    id: str
    kind: RuleKind
    name: str
    active: bool
    position: int
    actions: ActionsModel
    event: TriggerEvent | None
    conditions: list[ConditionModel]
    schedule: ScheduleModel | None
    last_run_at: datetime | None

    @classmethod
    def of(cls, rule: Rule) -> RuleResponse:
        return cls(
            id=rule.id,
            kind=rule.kind,
            name=rule.name,
            active=rule.active,
            position=rule.position,
            actions=ActionsModel.model_validate(asdict(rule.actions)),
            event=rule.event,
            conditions=[ConditionModel.model_validate(asdict(each)) for each in rule.conditions],
            schedule=ScheduleModel.model_validate(asdict(rule.schedule)) if rule.schedule else None,
            last_run_at=rule.last_run_at,
        )
