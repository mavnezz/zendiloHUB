from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from ..models.user import User


@dataclass(frozen=True)
class UserPage:
    items: Sequence[User]
    total: int


class UserRepository(Protocol):
    async def find(self, user_id: str) -> User | None: ...

    async def find_by_email(self, email: str) -> User | None: ...

    async def save(self, user: User) -> None:
        """Inserts or updates; raises EmailTakenError if another user has the address."""
        ...

    async def delete(self, user_id: str) -> None: ...

    async def count_admins(self) -> int: ...

    async def search(self, query: str, *, offset: int, limit: int, ids: Sequence[str] = ()) -> UserPage:
        """Users whose address contains `query` (and, if given, whose id is in `ids`), newest first."""
        ...
