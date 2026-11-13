"""
Synchronous contracts between modules: one module provides an implementation, another
module's infrastructure adapter calls it. (Asynchronous notifications are integration events.)
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from .domain.queue_rights import QueueRight


class Slot[T]:
    """A late-bound implementation: the providing module may be built after the one that uses it."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._implementation: T | None = None

    def provide(self, implementation: T) -> None:
        if self._implementation is not None:
            raise RuntimeError(f'{self._name} is already provided')
        self._implementation = implementation

    def get(self) -> T:
        if self._implementation is None:
            raise RuntimeError(f'No module provides {self._name}')
        return self._implementation


class Invitations(Protocol):
    """Provided by tenancy, used by identity: on a self-hosted instance only invited people may sign up."""

    async def pending_for(self, email: str) -> bool:
        """Whether an organization invited the address and the invitation has not expired."""
        ...


class Memberships(Protocol):
    """Provided by tenancy, used by access: only members of an organization can be in its groups."""

    async def is_member(self, tenant_id: str, user_id: str) -> bool: ...


class QueueAccess(Protocol):
    """
    Provided by access, used by every module that shows or changes what lies in queues (tickets from phase 2):
    what a person may do in which queue, as the union of their groups' rights. `all_queues` (the permission
    `queues.all`) gives every right in every queue.
    """

    async def rights(
        self, tenant_id: str, user_id: str, queue_id: str, *, all_queues: bool = False
    ) -> frozenset[QueueRight]:
        """Empty if the queue does not exist or the person may do nothing in it."""
        ...

    async def visible(
        self, tenant_id: str, user_id: str, *, all_queues: bool = False
    ) -> Mapping[str, frozenset[QueueRight]]:
        """The queues the person may at least `view`, by id, with their rights; for filtering lists in SQL."""
        ...


@dataclass(frozen=True)
class Contracts:
    """The slots modules provide for each other; added as modules need them."""

    invitations: Slot[Invitations] = field(default_factory=lambda: Slot('Invitations'))
    memberships: Slot[Memberships] = field(default_factory=lambda: Slot('Memberships'))
    queue_access: Slot[QueueAccess] = field(default_factory=lambda: Slot('QueueAccess'))

    @classmethod
    def empty(cls) -> Contracts:
        return cls()
