from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest

from zendilohub.modules.integrations.domain.models.webhook import QUEUES_MAX, InvalidWebhookError, Webhook


def webhook(**fields: Any) -> Webhook:
    base = Webhook(
        id='w1',
        tenant_id='t1',
        name='Chat',
        url='https://hooks.slack.example/x',
        events=('ticket.created',),
        active=True,
        created_at=datetime(2026, 11, 14, tzinfo=UTC),
    )
    return replace(base, **fields)


def test_checks_format_and_queues() -> None:
    hook = webhook(format='slack', queue_ids=('q1', 'q1', 'q2'))
    hook.check()
    assert hook.queue_ids == ('q1', 'q2')
    cases: list[tuple[dict[str, Any], str]] = [
        ({'format': 'xml'}, 'format'),
        ({'queue_ids': ('q',) * (QUEUES_MAX + 1)}, 'queue_ids'),
    ]
    for fields, field in cases:
        with pytest.raises(InvalidWebhookError) as raised:
            webhook(**fields).check()
        assert raised.value.params == {'field': field}


def test_wants_its_events_and_queues() -> None:
    hook = webhook(queue_ids=('q1',))
    assert hook.wants('ticket.created', 'q1')
    assert hook.wants('ticket.created', None)
    assert not hook.wants('ticket.created', 'q2')
    assert not hook.wants('ticket.changed', 'q1')
    assert webhook().wants('ticket.created', 'q2')
    assert not webhook(active=False).wants('ticket.created', 'q1')
