from dataclasses import dataclass
from datetime import datetime, timedelta

RESET_LIFETIME = timedelta(hours=1)


@dataclass(kw_only=True)
class PasswordReset:
    """A single-use password reset link; the id is the hash of the token in the link."""

    id: str
    user_id: str
    created_at: datetime
    expires_at: datetime

    @classmethod
    def issue(cls, *, id: str, user_id: str, now: datetime) -> PasswordReset:
        return cls(id=id, user_id=user_id, created_at=now, expires_at=now + RESET_LIFETIME)

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at
