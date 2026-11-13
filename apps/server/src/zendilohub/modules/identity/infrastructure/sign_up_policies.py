from zendilohub.core.contracts import Contracts


class OpenSignUp:
    """SaaS: everyone may sign up."""

    async def allows(self, email: str) -> bool:
        return True


class InvitedOnly:
    """A self-hosted instance: only addresses an organization invited (tenancy knows the invitations)."""

    def __init__(self, contracts: Contracts) -> None:
        self._contracts = contracts

    async def allows(self, email: str) -> bool:
        return await self._contracts.invitations.get().pending_for(email)
