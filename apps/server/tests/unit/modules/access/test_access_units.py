from datetime import UTC, datetime

import pytest

from zendilohub.core.domain.queue_rights import PRESETS, QUEUE_RIGHTS, ordered, preset_of
from zendilohub.modules.access.domain.exceptions import InvalidGroupError, InvalidQueueError, InvalidRightsError
from zendilohub.modules.access.domain.models.grant import Grant, checked_rights, union
from zendilohub.modules.access.domain.models.group import Group
from zendilohub.modules.access.domain.models.names import DESCRIPTION_MAX, NAME_MAX
from zendilohub.modules.access.domain.models.queue import Queue

NOW = datetime(2026, 11, 13, tzinfo=UTC)


def test_rights_have_one_order_and_ready_made_levels() -> None:
    assert ordered(['move', 'view', 'view', 'unknown']) == ('view', 'move')
    assert preset_of(['note', 'view']) == 'contribute'
    assert preset_of(QUEUE_RIGHTS) == 'full'
    assert preset_of(['view', 'move']) is None
    assert all(preset == ordered(preset) for preset in PRESETS.values())


def test_checks_the_rights_of_a_grant() -> None:
    assert checked_rights(['reply', 'view']) == ('view', 'reply')
    assert checked_rights([]) == ()
    with pytest.raises(InvalidRightsError):
        checked_rights(['view', 'fly'])


def test_rights_of_several_groups_add_up() -> None:
    grants = [
        Grant(group_id='g1', queue_id='q', rights=('view',)),
        Grant(group_id='g2', queue_id='q', rights=('view', 'reply')),
    ]
    assert union(grants) == frozenset({'view', 'reply'})
    assert union([]) == frozenset()


def test_checks_names_and_descriptions() -> None:
    queue = Queue.create(id='q', tenant_id='t', name='  Support \n desk ', description=' x ', now=NOW)
    assert (queue.name, queue.description) == ('Support desk', 'x')
    with pytest.raises(InvalidQueueError):
        queue.change(name='x' * (NAME_MAX + 1), description='', now=NOW)
    with pytest.raises(InvalidQueueError):
        Queue.create(id='q', tenant_id='t', name='Support', description='x' * (DESCRIPTION_MAX + 1), now=NOW)
    with pytest.raises(InvalidGroupError):
        Group.create(id='g', tenant_id='t', name='', description='', now=NOW)
