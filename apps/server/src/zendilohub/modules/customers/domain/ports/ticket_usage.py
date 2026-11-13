from typing import Protocol


class CustomerTickets(Protocol):
    """How many tickets a contact has (they are kept in the tickets module)."""

    async def of_customer(self, tenant_id: str, contact_id: str) -> int: ...
