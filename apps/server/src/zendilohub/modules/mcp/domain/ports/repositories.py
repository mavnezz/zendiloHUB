from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from zendilohub.core.domain.permissions import Permission

from ..models.connection import Connection


class ConnectionRepository(Protocol):
    async def of_member(self, tenant_id: str, user_id: str) -> Sequence[Connection]: ...

    async def find_by_hash(self, token_hash: str) -> Connection | None: ...

    async def save(self, connection: Connection) -> None: ...

    async def touch(self, connection_id: str, at: datetime) -> None: ...

    async def delete(self, tenant_id: str, user_id: str, connection_id: str) -> bool: ...

    async def forget(self, tenant_id: str | None, user_id: str | None) -> None:
        """A member left (tenant and user), an account went (user) or an organization (tenant)."""
        ...


class Members(Protocol):
    async def permissions_of(self, tenant_id: str, user_id: str) -> frozenset[Permission] | None:
        """None if no member (any more)."""
        ...
