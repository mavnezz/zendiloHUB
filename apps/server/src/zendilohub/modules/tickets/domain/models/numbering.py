"""How an organization numbers its tickets, as OTOBO's number generators and Zammad's ticket number settings do."""

import re
from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Literal, get_args

from zendilohub.core.domain.app_domain_error import ValidationError

type NumberFormat = Literal['increment', 'date']
NUMBER_FORMATS: tuple[NumberFormat, ...] = get_args(NumberFormat.__value__)

DEFAULT_START = 1001
START_MAX = 10**12
DATE_DIGITS = range(3, 7)
DEFAULT_PREFIX = '#'
PREFIX_PATTERN = re.compile(r'[A-Za-z0-9#\-_:]{1,16}')


class InvalidNumberingError(ValidationError):
    def __init__(self, field: str, params: dict[str, str | int | float] | None = None) -> None:
        super().__init__(
            'invalid_numbering', f'Please check the ticket numbers ({field})', {'field': field, **(params or {})}
        )


def check_digit(digits: str) -> int:
    """The Luhn check digit of a number: one mistyped digit or two swapped ones change it."""
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2 == 0:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return (10 - total % 10) % 10


@dataclass(frozen=True, kw_only=True)
class Counter:
    """What was handed out last: the running count, and the day and count of that day (date numbers)."""

    last: int = 0
    day: date | None = None
    day_count: int = 0


@dataclass(kw_only=True)
class Numbering:
    tenant_id: str
    format: NumberFormat = 'increment'
    start: int = DEFAULT_START
    """`increment`: the first number; numbers only ever grow from here."""
    date_digits: int = 4
    """`date`: the digits of the day's counter after YYYYMMDD (202611140001)."""
    checksum: bool = False
    """Appends a check digit, so a mistyped number in a subject finds no ticket."""
    prefix: str = DEFAULT_PREFIX
    """What stands before the number in e-mail subjects: `[#1001]`, `[Ticket#1001]`."""
    updated_at: datetime | None = None

    def check(self) -> None:
        if self.format not in NUMBER_FORMATS:
            raise InvalidNumberingError('format')
        if not 1 <= self.start <= START_MAX:
            raise InvalidNumberingError('start')
        if self.date_digits not in DATE_DIGITS:
            raise InvalidNumberingError('date_digits')
        self.prefix = self.prefix.strip()
        if not PREFIX_PATTERN.fullmatch(self.prefix):
            raise InvalidNumberingError('prefix')

    def issue(self, counter: Counter, today: date) -> tuple[int, Counter]:
        """The next number after `counter` and the counter that remembers it."""
        if self.format == 'date':
            count = counter.day_count + 1 if counter.day == today else 1
            following = replace(counter, day=today, day_count=count)
            base = f'{today:%Y%m%d}{count:0{self.date_digits}d}'
        else:
            value = max(counter.last + 1, self.start)
            following = replace(counter, last=value)
            base = str(value)
        if self.checksum:
            base += str(check_digit(base))
        return int(base), following

    def tag(self, number: int) -> str:
        return f'[{self.prefix}{number}]'
