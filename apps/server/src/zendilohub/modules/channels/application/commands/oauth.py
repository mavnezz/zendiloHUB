"""Connecting mailboxes with OAuth: off to the provider (start), back with a code (finish)."""

import base64
import hashlib
import secrets
from dataclasses import dataclass

from zendilohub.core.bus.message import Command, Query
from zendilohub.core.domain.clock import Clock
from zendilohub.core.domain.email_address import normalized_email
from zendilohub.core.domain.id_generator import IdGenerator

from ...domain.exceptions import (
    AccountNotFoundError,
    InvalidAccountError,
    OAuthFailedError,
    OAuthUnavailableError,
)
from ...domain.models.account import ACCOUNTS_MAX, EmailAccount, Provider
from ...domain.models.oauth import STATE_TTL, ConnectRequest
from ...domain.ports.repositories import AccountRepository, ConnectRequestRepository
from ...domain.ports.services import OAuthError, OAuthProviders
from .accounts import Vault


def _digest(state: str) -> str:
    return hashlib.sha256(state.encode()).hexdigest()


def _challenge(verifier: str) -> str:
    """PKCE S256."""
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()


@dataclass(frozen=True, kw_only=True)
class StartConnect(Command[str]):
    """Resolves to the provider's sign-in page the browser goes to."""

    tenant_id: str
    user_id: str
    provider: Provider
    redirect_uri: str
    account_id: str | None = None
    """Reconnect this account (or switch it to OAuth); None: a new account in `queue_id`."""
    queue_id: str | None = None
    name: str = ''
    display_name: str = ''


class StartConnectHandler:
    def __init__(
        self,
        accounts: AccountRepository,
        requests: ConnectRequestRepository,
        providers: OAuthProviders,
        clock: Clock,
    ) -> None:
        self._accounts = accounts
        self._requests = requests
        self._providers = providers
        self._clock = clock

    async def handle(self, command: StartConnect) -> str:
        if command.provider not in self._providers.configured():
            raise OAuthUnavailableError(command.provider)
        if command.account_id is not None:
            if await self._accounts.find(command.tenant_id, command.account_id) is None:
                raise AccountNotFoundError()
        elif command.queue_id is None:
            raise InvalidAccountError('queue_id')
        name, display_name = ' '.join(command.name.split()), ' '.join(command.display_name.split())
        now = self._clock.now()
        await self._requests.delete_expired(now)
        # The organization leads the state, so even a failed return finds its way back to its settings.
        state, verifier = f'{command.tenant_id}.{secrets.token_urlsafe(32)}', secrets.token_urlsafe(48)
        await self._requests.add(
            ConnectRequest(
                id=_digest(state),
                tenant_id=command.tenant_id,
                user_id=command.user_id,
                provider=command.provider,
                verifier=verifier,
                account_id=command.account_id,
                queue_id=command.queue_id,
                name=name,
                display_name=display_name,
                created_at=now,
                expires_at=now + STATE_TTL,
            )
        )
        return self._providers.authorize_url(
            command.provider, state=state, challenge=_challenge(verifier), redirect_uri=command.redirect_uri
        )


@dataclass(frozen=True)
class Connected:
    tenant_id: str
    account: EmailAccount
    created: bool


@dataclass(frozen=True, kw_only=True)
class FinishConnect(Command[Connected]):
    """The browser is back from the provider with a code (or the provider's error)."""

    state: str
    code: str | None
    error: str | None
    user_id: str | None
    """Who is logged in here: must be who started it."""
    redirect_uri: str


class FinishConnectHandler:
    def __init__(
        self,
        accounts: AccountRepository,
        requests: ConnectRequestRepository,
        providers: OAuthProviders,
        vault: Vault,
        ids: IdGenerator,
        clock: Clock,
    ) -> None:
        self._accounts = accounts
        self._requests = requests
        self._providers = providers
        self._vault = vault
        self._ids = ids
        self._clock = clock

    async def handle(self, command: FinishConnect) -> Connected:
        now = self._clock.now()
        request = await self._requests.take(_digest(command.state)) if command.state else None
        if request is None or request.is_expired(now):
            raise OAuthFailedError('expired')
        if command.user_id != request.user_id:
            raise OAuthFailedError('session')
        if command.error or not command.code:
            raise OAuthFailedError('denied' if command.error == 'access_denied' else 'provider')
        try:
            grant = await self._providers.exchange(
                request.provider, code=command.code, verifier=request.verifier, redirect_uri=command.redirect_uri
            )
        except OAuthError as error:
            raise OAuthFailedError(error.code) from None
        address = normalized_email(grant.address or '')
        if address is None:
            raise OAuthFailedError('no_address')
        if not grant.refresh_token:
            raise OAuthFailedError('no_refresh_token')

        account, created = await self._account(request, address)
        await self._accounts.save(account)
        await self._vault.store_tokens(account, grant)
        return Connected(request.tenant_id, account, created)

    async def _account(self, request: ConnectRequest, address: str) -> tuple[EmailAccount, bool]:
        now = self._clock.now()
        if request.account_id is not None:
            account = await self._accounts.find(request.tenant_id, request.account_id)
            if account is None:
                raise OAuthFailedError('account_gone')
            if await self._accounts.address_taken(request.tenant_id, address, except_id=account.id):
                raise OAuthFailedError('address_taken')
            account.reconnected(request.provider, address, now)
            return account, False
        if len(await self._accounts.of_tenant(request.tenant_id)) >= ACCOUNTS_MAX:
            raise OAuthFailedError('limit')
        if await self._accounts.address_taken(request.tenant_id, address):
            raise OAuthFailedError('address_taken')
        account = EmailAccount.connected(
            id=self._ids.new_id(),
            tenant_id=request.tenant_id,
            provider=request.provider,
            address=address,
            name=request.name,
            display_name=request.display_name,
            queue_id=request.queue_id or '',
            now=now,
        )
        return account, True


@dataclass(frozen=True)
class MailProviders(Query[tuple[Provider, ...]]):
    """The providers mailboxes can be connected with here."""


class MailProvidersHandler:
    def __init__(self, providers: OAuthProviders) -> None:
        self._providers = providers

    async def handle(self, _query: MailProviders) -> tuple[Provider, ...]:
        return self._providers.configured()
