from dataclasses import dataclass
from datetime import datetime, timedelta

from zendilohub.core.domain.app_domain_error import NotFoundError, UnauthenticatedError, ValidationError

LINK_LIFETIME = timedelta(minutes=30)
SESSION_LIFETIME = timedelta(days=30)


class InvalidPortalError(ValidationError):
    def __init__(self, field: str) -> None:
        super().__init__('invalid_portal', f'Please check the portal ({field})', {'field': field})


class PortalClosedError(NotFoundError):
    def __init__(self) -> None:
        super().__init__('portal_closed', 'This organization has no customer portal')


class PortalLoginRequiredError(UnauthenticatedError):
    def __init__(self) -> None:
        super().__init__('portal_login_required', 'Please log in to the portal')


class PortalTicketNotFoundError(NotFoundError):
    def __init__(self) -> None:
        super().__init__('ticket_not_found', 'The ticket does not exist')


class PortalLinkInvalidError(ValidationError):
    def __init__(self) -> None:
        super().__init__('portal_link_invalid', 'This link is invalid or has expired')


@dataclass(kw_only=True)
class PortalSettings:
    """Whether customers can log in (by a link sent to their address), where their new tickets go, what they see."""

    tenant_id: str
    enabled: bool = False
    queue_id: str | None = None
    company_tickets: bool = False
    """Contacts also see the tickets of the other contacts of their company."""

    def check(self) -> None:
        if self.enabled and not self.queue_id:
            raise InvalidPortalError('queue_id')


@dataclass(frozen=True, kw_only=True)
class PortalLogin:
    """A sign-in link or a session (only the token's hash is kept)."""

    token_hash: str
    tenant_id: str
    contact_id: str
    email: str
    expires_at: datetime
