from typing import Protocol


class PasswordHasher(Protocol):
    async def hash(self, password: str) -> str: ...

    async def verify(self, password: str, password_hash: str) -> bool: ...

    def needs_rehash(self, password_hash: str) -> bool:
        """True if the hash was made with weaker parameters than today's."""
        ...
