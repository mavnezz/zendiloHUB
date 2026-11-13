from dataclasses import dataclass
from datetime import datetime
from typing import Literal

type HistoryAction = Literal[
    'created',
    'changed',
    'message',
    'merged',
    'merged_from',
    'split_from',
    'linked',
    'unlinked',
    'time',
]


@dataclass(frozen=True, kw_only=True)
class HistoryEntry:
    """Who changed what in a ticket and when; never changed afterwards."""

    id: str
    tenant_id: str
    ticket_id: str
    actor_id: str | None
    actor_name: str
    action: HistoryAction
    field: str | None
    old: str | None
    new: str | None
    created_at: datetime
