from datetime import date

import pytest

from zendilohub.modules.tickets.domain.models.numbering import (
    Counter,
    InvalidNumberingError,
    Numbering,
    check_digit,
)

DAY = date(2026, 11, 14)


def test_check_digit_is_luhn() -> None:
    assert [check_digit(each) for each in ('7992739871', '1001', '0')] == [3, 7, 0]


def test_increment_counts_up_from_the_start() -> None:
    numbering = Numbering(tenant_id='t', start=10000)
    number, counter = numbering.issue(Counter(), DAY)
    assert (number, counter.last) == (10000, 10000)
    assert numbering.issue(counter, DAY)[0] == 10001
    assert numbering.issue(Counter(last=20000), DAY)[0] == 20001


def test_date_numbers_restart_each_day() -> None:
    numbering = Numbering(tenant_id='t', format='date', date_digits=4)
    number, counter = numbering.issue(Counter(), DAY)
    assert (number, counter.day, counter.day_count) == (202611140001, DAY, 1)
    assert numbering.issue(counter, DAY)[0] == 202611140002
    assert numbering.issue(counter, date(2026, 11, 15))[0] == 202611150001
    # More tickets than digits: the counter simply gets longer.
    assert numbering.issue(Counter(day=DAY, day_count=9999), DAY)[0] == 2026111410000


def test_check_digit_and_tag() -> None:
    numbering = Numbering(tenant_id='t', checksum=True, prefix='Ticket#')
    number, _ = numbering.issue(Counter(), DAY)
    assert (number, numbering.tag(number)) == (10017, '[Ticket#10017]')


@pytest.mark.parametrize(
    ('changes', 'field'),
    [
        ({'format': 'random'}, 'format'),
        ({'start': 0}, 'start'),
        ({'date_digits': 2}, 'date_digits'),
        ({'prefix': ''}, 'prefix'),
        ({'prefix': 'x' * 17}, 'prefix'),
        ({'prefix': 'Tick et'}, 'prefix'),
    ],
)
def test_check_refuses_bad_settings(changes: dict[str, object], field: str) -> None:
    numbering = Numbering(tenant_id='t', **changes)  # type: ignore[arg-type]
    with pytest.raises(InvalidNumberingError) as raised:
        numbering.check()
    assert raised.value.params == {'field': field}


def test_check_trims_the_prefix() -> None:
    numbering = Numbering(tenant_id='t', prefix=' ZH- ')
    numbering.check()
    assert numbering.prefix == 'ZH-'
