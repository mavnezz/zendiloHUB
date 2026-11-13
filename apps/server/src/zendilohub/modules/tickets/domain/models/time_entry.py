from dataclasses import dataclass
from datetime import datetime

from ..exceptions import InvalidTicketError

MINUTES_MAX = 24 * 60


@dataclass(frozen=True, kw_only=True)
class TimeEntry:
    """Time someone spent on a ticket (like Zammad's time accounting)."""

    id: str
    tenant_id: str
    ticket_id: str
    user_id: str
    minutes: int
    message_id: str | None
    created_at: datetime

    @classmethod
    def record(
        cls,
        *,
        id: str,
        tenant_id: str,
        ticket_id: str,
        user_id: str,
        minutes: int,
        message_id: str | None,
        now: datetime,
    ) -> TimeEntry:
        if not 1 <= minutes <= MINUTES_MAX:
            raise InvalidTicketError('minutes')
        return cls(
            id=id,
            tenant_id=tenant_id,
            ticket_id=ticket_id,
            user_id=user_id,
            minutes=minutes,
            message_id=message_id,
            created_at=now,
        )
