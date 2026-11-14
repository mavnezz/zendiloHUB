import re
from dataclasses import dataclass
from datetime import datetime

from zendilohub.core.domain.app_domain_error import NotFoundError, ValidationError

PREFIX = 'zhm_'
CONNECTIONS_MAX = 10
"""Per member and organization."""


class InvalidConnectionError(ValidationError):
    def __init__(self, field: str) -> None:
        super().__init__('invalid_connection', f'Please check the connection ({field})', {'field': field})


class ConnectionNotFoundError(NotFoundError):
    def __init__(self) -> None:
        super().__init__('connection_not_found', 'The connection does not exist')


@dataclass(kw_only=True)
class Connection:
    """
    An AI assistant (Claude, ChatGPT, …) a member connected: it works in the organization for them, with their groups'
    rights and their role's permissions as they are at each call. Only the token's hash is kept.
    """

    id: str
    tenant_id: str
    user_id: str
    email: str
    name: str
    token_hash: str
    start: str
    """The first characters of the token, to tell connections apart."""
    created_at: datetime
    last_used_at: datetime | None = None

    def check(self) -> None:
        self.name = ' '.join(self.name.split())
        if not 1 <= len(self.name) <= 80 or not re.match(r'^[\w .()+/-]+$', self.name):
            raise InvalidConnectionError('name')
