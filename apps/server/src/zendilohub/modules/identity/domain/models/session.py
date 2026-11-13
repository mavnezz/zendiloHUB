from dataclasses import dataclass
from datetime import datetime, timedelta

SESSION_LIFETIME = timedelta(days=30)


@dataclass(frozen=True, kw_only=True)
class Session:
    """
    A login session. Its id is a one-way hash of the session token, so a leaked
    database does not leak usable tokens.
    """

    id: str
    user_id: str
    created_at: datetime
    expires_at: datetime

    @classmethod
    def start(cls, *, id: str, user_id: str, now: datetime) -> Session:
        return cls(id=id, user_id=user_id, created_at=now, expires_at=now + SESSION_LIFETIME)

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at
