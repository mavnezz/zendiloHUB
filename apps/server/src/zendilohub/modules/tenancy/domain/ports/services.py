from dataclasses import dataclass
from typing import Protocol

from ..models.invitation import Invitation
from ..models.tenant import Tenant


@dataclass(frozen=True)
class IssuedToken:
    token: str
    """Goes into the e-mail link; never stored."""
    hash: str


class TokenService(Protocol):
    def issue(self) -> IssuedToken: ...

    def hash_of(self, token: str) -> str: ...


class InvitationNotifier(Protocol):
    async def invite(
        self, invitation: Invitation, tenant: Tenant, *, inviter: str, link: str, role_name: str | None = None
    ) -> None:
        """Sends the invitation; `inviter` is the inviting member's e-mail address, `role_name` that of an own role."""
        ...
