from typing import Protocol

from ..models.registration import Registration
from ..models.user import User


class AccountNotifier(Protocol):
    """Sends the account e-mails; `link` is the absolute URL the user has to open."""

    async def confirm_registration(self, registration: Registration, link: str) -> None: ...

    async def already_registered(self, user: User, link: str) -> None:
        """Someone signed up with an address that has an account: point to the login and the password reset."""
        ...

    async def reset_password(self, user: User, link: str) -> None: ...
