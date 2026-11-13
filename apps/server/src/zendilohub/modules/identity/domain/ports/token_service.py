from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class IssuedToken:
    token: str
    """Goes to the user (cookie, e-mail link); never stored."""
    id: str
    """The stored one-way hash of the token."""


class TokenService(Protocol):
    def issue(self) -> IssuedToken: ...

    def id_of(self, token: str) -> str: ...
