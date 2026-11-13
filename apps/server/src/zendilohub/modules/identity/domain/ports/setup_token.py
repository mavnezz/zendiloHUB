from typing import Protocol


class SetupTokens(Protocol):
    """
    The one-time code that guards the setup wizard of a self-hosted instance: whoever reaches the instance first
    must not be able to take it over, so the wizard asks for the code the server writes to its log.
    """

    def issue(self) -> str:
        """The current code; made on the first call and kept until the setup is done."""
        ...

    def matches(self, token: str) -> bool: ...

    def discard(self) -> None: ...
