"""
What a group may do in a queue. Shared by every module that works with queues (access grants the rights, tickets and
conversations check them), so all of them speak the same words.
"""

from collections.abc import Iterable
from typing import Literal, get_args

type QueueRight = Literal['view', 'create', 'note', 'reply', 'edit', 'assign', 'move']
"""
`view`: see and search the queue's tickets; `create`: open tickets in it and move tickets into it; `note`: internal
notes; `reply`: answer customers; `edit`: status, priority, tags, fields, close; `assign`: give tickets to someone;
`move`: move tickets out of the queue.
"""

QUEUE_RIGHTS: tuple[QueueRight, ...] = get_args(QueueRight.__value__)

type RightsPreset = Literal['read', 'contribute', 'work', 'full']

PRESETS: dict[RightsPreset, tuple[QueueRight, ...]] = {
    'read': ('view',),
    'contribute': ('view', 'note'),
    'work': ('view', 'create', 'note', 'reply', 'edit'),
    'full': QUEUE_RIGHTS,
}
"""The ready-made levels of the rights matrix; anything else is a custom set."""


def ordered(rights: Iterable[str]) -> tuple[QueueRight, ...]:
    """The known rights among `rights`, once each, in their canonical order."""
    given = set(rights)
    return tuple(right for right in QUEUE_RIGHTS if right in given)


def preset_of(rights: Iterable[str]) -> RightsPreset | None:
    """The preset these rights are exactly, if any."""
    canonical = ordered(rights)
    return next((name for name, preset in PRESETS.items() if preset == canonical), None)
