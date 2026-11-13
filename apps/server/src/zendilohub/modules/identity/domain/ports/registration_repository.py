from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from ..models.registration import Registration


class RegistrationRepository(Protocol):
    async def find(self, registration_id: str) -> Registration | None: ...

    async def find_by_email(self, email: str) -> Sequence[Registration]:
        """Several people may have signed up with the same address; newest first."""
        ...

    async def save(self, registration: Registration) -> None: ...

    async def delete(self, registration_id: str) -> None: ...

    async def delete_by_email(self, email: str) -> None: ...

    async def delete_expired(self, now: datetime) -> None: ...
