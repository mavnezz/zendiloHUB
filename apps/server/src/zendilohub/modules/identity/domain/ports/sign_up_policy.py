from typing import Protocol


class SignUpPolicy(Protocol):
    """Who may create an account: everyone (SaaS) or only invited people (a self-hosted instance)."""

    async def allows(self, email: str) -> bool: ...
