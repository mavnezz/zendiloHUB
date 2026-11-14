from dataclasses import dataclass
from datetime import datetime, timedelta

CHALLENGE_LIFETIME = timedelta(minutes=5)
MAX_ATTEMPTS = 5


@dataclass(kw_only=True)
class LoginChallenge:
    """
    The password was right and the account has two-factor login: the session starts once the code is right too.
    Its id is a one-way hash of the token the browser holds.
    """

    id: str
    user_id: str
    expires_at: datetime
    attempts: int = 0

    @classmethod
    def start(cls, *, id: str, user_id: str, now: datetime) -> LoginChallenge:
        return cls(id=id, user_id=user_id, expires_at=now + CHALLENGE_LIFETIME)

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at

    def fail(self) -> bool:
        """Counts a wrong code; True while more attempts are left."""
        self.attempts += 1
        return self.attempts < MAX_ATTEMPTS
