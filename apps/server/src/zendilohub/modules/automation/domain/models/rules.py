from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Literal, get_args

from zendilohub.core.domain.automation import AutomationChanges, TicketCriteria, TicketFacts
from zendilohub.core.domain.email_address import normalized_email

from ..exceptions import InvalidRuleError

type RuleKind = Literal['macro', 'trigger', 'schedule']
type TriggerEvent = Literal['created', 'customer_replied', 'updated']
TRIGGER_EVENTS: tuple[TriggerEvent, ...] = get_args(TriggerEvent.__value__)
type ConditionField = Literal['queue_id', 'state', 'priority', 'channel', 'tags', 'subject', 'customer_email', 'owner']
CONDITION_FIELDS: tuple[ConditionField, ...] = get_args(ConditionField.__value__)
type ConditionOperator = Literal['is', 'is_not', 'contains', 'not_contains', 'is_set', 'is_not_set']
CONDITION_OPERATORS: tuple[ConditionOperator, ...] = get_args(ConditionOperator.__value__)
STATES = ('new', 'open', 'pending_reminder', 'pending_close', 'closed')
PRIORITIES = ('low', 'normal', 'high', 'urgent')
RULES_MAX = 100
TEXT_MAX = 10_000
NOTIFY_EMAILS_MAX = 10
NOTIFY_TEXT_MAX = 2000


@dataclass(frozen=True, kw_only=True)
class RuleCondition:
    field: ConditionField
    operator: ConditionOperator
    value: str = ''

    def check(self) -> None:
        if self.field not in CONDITION_FIELDS:
            raise InvalidRuleError('conditions.field')
        if self.operator not in CONDITION_OPERATORS:
            raise InvalidRuleError('conditions.operator')
        if self.operator not in ('is_set', 'is_not_set') and not self.value.strip():
            raise InvalidRuleError('conditions.value')
        if len(self.value) > 500:
            raise InvalidRuleError('conditions.value')

    def holds(self, facts: TicketFacts) -> bool:
        value = self.value.strip().lower()
        if self.field == 'owner':
            return (facts.owner_id is not None) == (self.operator in ('is_set', 'is'))
        if self.field == 'tags':
            found = value in facts.tags
            return not found if self.operator in ('not_contains', 'is_not') else found
        actual = {
            'queue_id': facts.queue_id,
            'state': facts.state,
            'priority': facts.priority,
            'channel': facts.channel,
            'subject': facts.subject,
            'customer_email': facts.customer_email or '',
        }[self.field].lower()
        match self.operator:
            case 'is':
                return actual == value
            case 'is_not':
                return actual != value
            case 'contains':
                return value in actual
            case 'not_contains':
                return value not in actual
            case 'is_set':
                return bool(actual)
            case _:
                return not actual


@dataclass(frozen=True, kw_only=True)
class Schedule:
    """When a scheduled job takes a ticket: its state and age (like OTOBO's generic agent)."""

    states: tuple[str, ...] = ()
    queue_ids: tuple[str, ...] = ()
    priorities: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    owner: Literal['any', 'none', 'set'] = 'any'
    idle_hours: int | None = None
    """No change for this long."""
    age_hours: int | None = None
    """Opened this long ago."""
    pending_passed: bool = False

    def check(self) -> None:
        if any(state not in STATES for state in self.states):
            raise InvalidRuleError('schedule.states')
        if any(priority not in PRIORITIES for priority in self.priorities):
            raise InvalidRuleError('schedule.priorities')
        for hours, field in ((self.idle_hours, 'idle_hours'), (self.age_hours, 'age_hours')):
            if hours is not None and not 1 <= hours <= 24 * 365:
                raise InvalidRuleError(f'schedule.{field}')
        if not (self.states or self.queue_ids or self.idle_hours or self.age_hours or self.pending_passed or self.tags):
            # A job on every open ticket at once is almost always a mistake.
            raise InvalidRuleError('schedule')

    def criteria(self, now: datetime) -> TicketCriteria:
        return TicketCriteria(
            states=self.states,
            queue_ids=self.queue_ids,
            priorities=self.priorities,
            tags=self.tags,
            owner=self.owner,
            updated_before=now - timedelta(hours=self.idle_hours) if self.idle_hours else None,
            created_before=now - timedelta(hours=self.age_hours) if self.age_hours else None,
            pending_passed=self.pending_passed,
        )


@dataclass(frozen=True, kw_only=True)
class Actions:
    """What a rule does; `owner_me` (macros only) gives the ticket to whoever applies the macro."""

    state: str | None = None
    pending_hours: int | None = None
    priority: str | None = None
    queue_id: str | None = None
    owner_id: str | None = None
    owner_me: bool = False
    unassign: bool = False
    add_tags: tuple[str, ...] = ()
    remove_tags: tuple[str, ...] = ()
    note: str = ''
    reply: str = ''
    notify_emails: tuple[str, ...] = ()
    """Triggers: an alert by e-mail to these addresses (e.g. an on-call inbox), with `notify_text` on top."""
    notify_text: str = ''

    def normalized(self) -> Actions:
        """The alert addresses trimmed, in lower case and once each (invalid ones stay, so `check` finds them)."""
        emails = tuple(dict.fromkeys(normalized_email(each) or each for each in self.notify_emails))
        return replace(self, notify_emails=emails, notify_text=self.notify_text.strip())

    def check(self, kind: RuleKind) -> None:
        if self.state is not None and self.state not in STATES:
            raise InvalidRuleError('actions.state')
        if self.pending_hours is not None and not 1 <= self.pending_hours <= 24 * 365:
            raise InvalidRuleError('actions.pending_hours')
        if self.priority is not None and self.priority not in PRIORITIES:
            raise InvalidRuleError('actions.priority')
        if self.owner_me and kind != 'macro':
            raise InvalidRuleError('actions.owner_me')
        if self.reply and kind == 'macro':
            # A macro's text to the customer goes through the composer, so the agent sees it before it goes out.
            raise InvalidRuleError('actions.reply')
        if len(self.note) > TEXT_MAX or len(self.reply) > TEXT_MAX:
            raise InvalidRuleError('actions.note')
        if any(len(tag) > 50 for tag in (*self.add_tags, *self.remove_tags)):
            raise InvalidRuleError('actions.tags')
        if self.notify_emails and kind != 'trigger':
            # A scheduled job runs on the same tickets every few minutes: its alerts would never stop.
            raise InvalidRuleError('actions.notify_emails')
        if len(self.notify_emails) > NOTIFY_EMAILS_MAX or any(
            normalized_email(each) != each for each in self.notify_emails
        ):
            raise InvalidRuleError('actions.notify_emails')
        if len(self.notify_text) > NOTIFY_TEXT_MAX:
            raise InvalidRuleError('actions.notify_text')
        if self.notify_text and not self.notify_emails:
            raise InvalidRuleError('actions.notify_emails')
        if self == Actions():
            raise InvalidRuleError('actions')

    def changes(self) -> AutomationChanges:
        return AutomationChanges(
            state=self.state,
            pending_hours=self.pending_hours,
            priority=self.priority,
            queue_id=self.queue_id,
            owner_id=self.owner_id,
            unassign=self.unassign,
            add_tags=self.add_tags,
            remove_tags=self.remove_tags,
            note=self.note or None,
            reply=self.reply or None,
        )


@dataclass(kw_only=True)
class Rule:
    """
    A macro (several changes with one click, like Zammad's), a trigger (on an event: if the conditions hold, the
    actions run) or a scheduled job (every few minutes on the tickets that fit).
    """

    id: str
    tenant_id: str
    kind: RuleKind
    name: str
    active: bool
    position: int
    actions: Actions
    event: TriggerEvent | None = None
    conditions: tuple[RuleCondition, ...] = ()
    schedule: Schedule | None = None
    last_run_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    def check(self) -> None:
        self.name = ' '.join(self.name.split())
        if not 1 <= len(self.name) <= 80:
            raise InvalidRuleError('name')
        self.actions = self.actions.normalized()
        self.actions.check(self.kind)
        if self.kind == 'trigger':
            if self.event not in TRIGGER_EVENTS:
                raise InvalidRuleError('event')
            if len(self.conditions) > 10:
                raise InvalidRuleError('conditions')
            for condition in self.conditions:
                condition.check()
        else:
            self.event, self.conditions = None, ()
        if self.kind == 'schedule':
            if self.schedule is None:
                raise InvalidRuleError('schedule')
            self.schedule.check()
        else:
            self.schedule = None

    def applies_to(self, event: TriggerEvent, facts: TicketFacts) -> bool:
        return self.active and self.event == event and all(each.holds(facts) for each in self.conditions)

    def with_actions(self, actions: Actions) -> Rule:
        return replace(self, actions=actions)
