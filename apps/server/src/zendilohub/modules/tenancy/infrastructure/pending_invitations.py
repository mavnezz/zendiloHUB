from zendilohub.core.domain.clock import Clock

from ..domain.ports.repositories import InvitationRepository


class PendingInvitations:
    """Tenancy's side of the `Invitations` contract: identity asks it before a sign-up on a self-hosted instance."""

    def __init__(self, invitations: InvitationRepository, clock: Clock) -> None:
        self._invitations = invitations
        self._clock = clock

    async def pending_for(self, email: str) -> bool:
        return await self._invitations.pending_for(email.strip().lower(), self._clock.now())
