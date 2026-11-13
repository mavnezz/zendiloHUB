import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, get_args

from ..exceptions import InvalidFilterError
from .email import ParsedEmail

type FilterField = Literal['from', 'to', 'cc', 'subject', 'body', 'header']
FILTER_FIELDS: tuple[FilterField, ...] = get_args(FilterField.__value__)
type Operator = Literal['contains', 'not_contains', 'equals', 'starts_with', 'ends_with', 'regex']
OPERATORS: tuple[Operator, ...] = get_args(Operator.__value__)
FILTERS_MAX = 100
CONDITIONS_MAX = 10


@dataclass(frozen=True, kw_only=True)
class Condition:
    field: FilterField
    operator: Operator
    value: str
    header: str = ''
    """For `header`: which one, e.g. `X-Spam-Flag`."""

    def check(self) -> None:
        if self.field not in FILTER_FIELDS:
            raise InvalidFilterError('conditions.field')
        if self.operator not in OPERATORS:
            raise InvalidFilterError('conditions.operator')
        if not self.value or len(self.value) > 500:
            raise InvalidFilterError('conditions.value')
        if self.field == 'header' and not re.fullmatch(r'[A-Za-z0-9-]{1,80}', self.header):
            raise InvalidFilterError('conditions.header')
        if self.operator == 'regex':
            try:
                re.compile(self.value)
            except re.error:
                raise InvalidFilterError('conditions.value') from None

    def matches(self, mail: ParsedEmail) -> bool:
        values = {
            'from': [mail.from_address, mail.from_name],
            'to': list(mail.to),
            'cc': list(mail.cc),
            'subject': [mail.subject],
            'body': [mail.text],
            'header': [mail.headers.get(self.header.lower(), '')],
        }[self.field]
        return (
            any(self._test(value) for value in values)
            if self.operator != 'not_contains'
            else all(self._test(value) for value in values)
        )

    def _test(self, value: str) -> bool:
        text, wanted = value.lower(), self.value.lower()
        match self.operator:
            case 'contains':
                return wanted in text
            case 'not_contains':
                return wanted not in text
            case 'equals':
                return text == wanted
            case 'starts_with':
                return text.startswith(wanted)
            case 'ends_with':
                return text.endswith(wanted)
            case _:
                return re.search(self.value, value, re.IGNORECASE) is not None


@dataclass(frozen=True, kw_only=True)
class FilterActions:
    queue_id: str | None = None
    priority: Literal['low', 'normal', 'high', 'urgent'] | None = None
    tags: tuple[str, ...] = ()
    ignore: bool = False
    """Drop the e-mail (spam, newsletters): no ticket, no reply."""


@dataclass(kw_only=True)
class MailFilter:
    """
    A rule for incoming mail (like OTOBO's postmaster filters): if its conditions match (all, or any), it routes the
    mail to a queue, sets the priority, adds tags or drops it. Filters run in order; `stop` ends the run.
    """

    id: str
    tenant_id: str
    name: str
    position: int
    active: bool
    match: Literal['all', 'any']
    conditions: tuple[Condition, ...]
    actions: FilterActions
    stop: bool
    created_at: datetime
    updated_at: datetime = field(compare=False)

    def check(self) -> None:
        self.name = ' '.join(self.name.split())
        if not 1 <= len(self.name) <= 80:
            raise InvalidFilterError('name')
        if not 1 <= len(self.conditions) <= CONDITIONS_MAX:
            raise InvalidFilterError('conditions')
        for condition in self.conditions:
            condition.check()
        actions = self.actions
        if not (actions.queue_id or actions.priority or actions.tags or actions.ignore):
            raise InvalidFilterError('actions')

    def matches(self, mail: ParsedEmail) -> bool:
        results = (condition.matches(mail) for condition in self.conditions)
        return all(results) if self.match == 'all' else any(results)


@dataclass(frozen=True)
class Routing:
    """What the filters decided for one e-mail."""

    queue_id: str | None = None
    priority: str | None = None
    tags: tuple[str, ...] = ()
    ignore: bool = False


def route(filters: list[MailFilter], mail: ParsedEmail) -> Routing:
    queue_id: str | None = None
    priority: str | None = None
    tags: list[str] = []
    for each in sorted(filters, key=lambda item: item.position):
        if not each.active or not each.matches(mail):
            continue
        if each.actions.ignore:
            return Routing(ignore=True)
        queue_id = each.actions.queue_id or queue_id
        priority = each.actions.priority or priority
        tags.extend(each.actions.tags)
        if each.stop:
            break
    return Routing(queue_id, priority, tuple(dict.fromkeys(tags)))
