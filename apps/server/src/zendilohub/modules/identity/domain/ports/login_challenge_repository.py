from datetime import datetime
from typing import Protocol

from ..models.login_challenge import LoginChallenge


class LoginChallengeRepository(Protocol):
    async def find(self, challenge_id: str) -> LoginChallenge | None: ...

    async def save(self, challenge: LoginChallenge) -> None:
        """Inserts or updates (the attempts)."""
        ...

    async def delete(self, challenge_id: str) -> None: ...

    async def delete_for_user(self, user_id: str) -> None: ...

    async def delete_expired(self, now: datetime) -> None: ...
