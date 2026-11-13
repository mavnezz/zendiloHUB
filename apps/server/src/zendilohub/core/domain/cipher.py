"""Seals what the app must use but never show again, such as the API keys of an organization."""

from typing import Protocol


class Cipher(Protocol):
    def seal(self, plain: str, *, context: str) -> bytes:
        """`context` binds the value to its place (e.g. organization and name): it opens nowhere else."""
        ...

    def open(self, sealed: bytes, *, context: str) -> str | None:
        """None if it was sealed with another key or for another context."""
        ...
