"""
Synchronous contracts between modules: one module provides an implementation, another
module's infrastructure adapter calls it. (Asynchronous notifications are integration events.)
"""

from dataclasses import dataclass, field
from typing import Protocol


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


@dataclass(frozen=True)
class Contracts:
    """The slots modules provide for each other; added as modules need them."""

    invitations: Slot[Invitations] = field(default_factory=lambda: Slot('Invitations'))

    @classmethod
    def empty(cls) -> Contracts:
        return cls()
