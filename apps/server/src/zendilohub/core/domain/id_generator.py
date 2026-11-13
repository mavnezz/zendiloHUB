from typing import Protocol


class IdGenerator(Protocol):
    def new_id(self) -> str:
        """A new, unique and time-ordered id (a UUID)."""
        ...
