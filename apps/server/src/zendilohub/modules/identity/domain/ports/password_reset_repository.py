from datetime import datetime
from typing import Protocol

from ..models.password_reset import PasswordReset


class PasswordResetRepository(Protocol):
    async def find(self, reset_id: str) -> PasswordReset | None: ...

    async def save(self, reset: PasswordReset) -> None: ...

    async def delete_for_user(self, user_id: str) -> None: ...

    async def delete_expired(self, now: datetime) -> None: ...
