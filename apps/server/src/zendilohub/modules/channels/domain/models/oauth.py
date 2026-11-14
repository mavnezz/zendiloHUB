"""Mailboxes connected with OAuth (Google, Microsoft 365) instead of a password."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from .account import PROVIDERS as PROVIDERS
from .account import SERVERS as SERVERS
from .account import Provider

STATE_TTL = timedelta(minutes=10)
REFRESH_EARLY = timedelta(seconds=60)
"""An access token that runs out sooner than this is renewed before use."""


@dataclass(frozen=True, kw_only=True)
class ConnectRequest:
    """What an administrator asked for before going to the provider: a new account, or to reconnect one."""

    id: str
    """SHA-256 of the state sent to the provider."""
    tenant_id: str
    user_id: str
    provider: Provider
    verifier: str
    """The PKCE code verifier."""
    account_id: str | None
    """Reconnect this account; None: create one."""
    queue_id: str | None
    name: str
    display_name: str
    created_at: datetime
    expires_at: datetime

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at


@dataclass(frozen=True, kw_only=True)
class AccessToken:
    token: str
    expires_at: datetime

    def usable(self, now: datetime) -> bool:
        return now + REFRESH_EARLY < self.expires_at


def token_context(tenant_id: str, account_id: str, kind: Literal['refresh', 'access']) -> str:
    return f'channels.account.{tenant_id}.{account_id}.oauth_{kind}'
