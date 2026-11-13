from dataclasses import dataclass
from typing import Literal

type LinkKind = Literal['related', 'parent', 'child']
"""Seen from the ticket: the other one is related to it, its parent or its child."""

OPPOSITE: dict[LinkKind, LinkKind] = {'related': 'related', 'parent': 'child', 'child': 'parent'}


@dataclass(frozen=True, kw_only=True)
class Link:
    ticket_id: str
    other_id: str
    kind: LinkKind
