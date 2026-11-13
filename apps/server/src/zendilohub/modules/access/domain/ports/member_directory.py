from typing import Protocol


class MemberDirectory(Protocol):
    """Who belongs to an organization (tenancy knows it)."""

    async def is_member(self, tenant_id: str, user_id: str) -> bool: ...
