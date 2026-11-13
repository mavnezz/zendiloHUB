from collections.abc import Iterable
from dataclasses import dataclass

from zendilohub.core.domain.queue_rights import QUEUE_RIGHTS, QueueRight, ordered

from ..exceptions import InvalidRightsError


@dataclass(frozen=True, kw_only=True)
class Grant:
    """What one group may do in one queue. No grant: nothing."""

    group_id: str
    queue_id: str
    rights: tuple[QueueRight, ...]


def checked_rights(rights: Iterable[str]) -> tuple[QueueRight, ...]:
    """The rights in their canonical order; raises for an unknown one. Empty means: take the grant away."""
    rights = list(rights)
    for right in rights:
        if right not in QUEUE_RIGHTS:
            raise InvalidRightsError(right)
    return ordered(rights)


def union(grants: Iterable[Grant]) -> frozenset[QueueRight]:
    """What a person may do through all their groups' grants: rights add up, nothing takes one away."""
    return frozenset(right for grant in grants for right in grant.rights)
