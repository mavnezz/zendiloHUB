from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta

from zendilohub.core.bus.message import Command
from zendilohub.core.domain.cipher import Cipher
from zendilohub.core.domain.clock import Clock
from zendilohub.core.domain.id_generator import IdGenerator

from ...domain.exceptions import AccountAddressTakenError, AccountNotFoundError, InvalidAccountError
from ...domain.models.account import (
    ACCOUNTS_MAX,
    AccountSettings,
    EmailAccount,
    Passwords,
    ServerKind,
    sealing_context,
)
from ...domain.models.oauth import AccessToken, token_context
from ...domain.ports.repositories import AccountRepository, OAuthTokens
from ...domain.ports.services import Credential, Mailbox, MailboxError, OAuthError, OAuthProviders, Outbox, TokenGrant


class Vault:
    """The accounts' passwords and OAuth tokens, sealed at rest; hands out what logs in to the mail servers."""

    def __init__(self, accounts: AccountRepository, cipher: Cipher, providers: OAuthProviders, clock: Clock) -> None:
        self._accounts = accounts
        self._cipher = cipher
        self._providers = providers
        self._clock = clock

    async def store(self, account: EmailAccount, passwords: Passwords) -> None:
        if account.provider is not None:
            return
        kinds: tuple[tuple[ServerKind, str | None], ...] = (('imap', passwords.imap), ('smtp', passwords.smtp))
        for kind, password in kinds:
            if password is not None:
                if len(password) > 1000:
                    raise InvalidAccountError(f'{kind}.password')
                sealed = self._cipher.seal(password, context=sealing_context(account.id, kind))
                await self._accounts.set_password(account.id, kind, sealed)

    async def password(self, account: EmailAccount, kind: ServerKind) -> str:
        """Empty without one (or if the secret key changed: it has to be entered again)."""
        sealed = await self._accounts.password(account.id, kind)
        if sealed is None:
            return ''
        return self._cipher.open(sealed, context=sealing_context(account.id, kind)) or ''

    async def credential(self, account: EmailAccount, kind: ServerKind) -> Credential:
        """
        The password, or a fresh OAuth access token (renewed when it runs out soon). Raises MailboxError when the
        provider refuses; when it refuses for good the account is marked to be connected again (and saved).
        """
        if account.provider is None:
            return Credential(await self.password(account, kind))
        if account.needs_reconnect:
            raise MailboxError('The mailbox must be connected again')
        context = (account.tenant_id, account.id)
        tokens = await self._accounts.oauth_tokens(account.id)
        now = self._clock.now()
        if tokens.access is not None and tokens.access_expires_at is not None:
            access = self._cipher.open(tokens.access, context=token_context(*context, 'access'))
            if access and AccessToken(token=access, expires_at=tokens.access_expires_at).usable(now):
                return Credential(access, oauth=True)
        refresh = (
            self._cipher.open(tokens.refresh, context=token_context(*context, 'refresh')) if tokens.refresh else None
        )
        if not refresh:
            return await self._disconnect(account, 'The mailbox must be connected again')
        try:
            grant = await self._providers.refresh(account.provider, refresh)
        except OAuthError as error:
            if error.code in ('invalid_grant', 'unauthorized_client', 'invalid_client'):
                return await self._disconnect(account, f'The provider ended the connection ({error.code})')
            raise MailboxError(f'The provider could not renew the access ({error.code})') from None
        await self.store_tokens(account, grant)
        return Credential(grant.access_token, oauth=True)

    async def store_tokens(self, account: EmailAccount, grant: TokenGrant) -> None:
        """Seals the access token and the refresh token (if the provider sent a new one, it replaces the old)."""
        context = (account.tenant_id, account.id)
        tokens = await self._accounts.oauth_tokens(account.id)
        refresh = (
            self._cipher.seal(grant.refresh_token, context=token_context(*context, 'refresh'))
            if grant.refresh_token
            else tokens.refresh
        )
        access = self._cipher.seal(grant.access_token, context=token_context(*context, 'access'))
        expires_at = self._clock.now() + timedelta(seconds=max(0, grant.expires_in))
        await self._accounts.set_oauth_tokens(account.id, OAuthTokens(refresh, access, expires_at))

    async def _disconnect(self, account: EmailAccount, reason: str) -> Credential:
        account.disconnected(reason, self._clock.now())
        await self._accounts.save(account)
        await self._accounts.set_oauth_tokens(account.id, OAuthTokens(None, None, None))
        raise MailboxError(reason)


@dataclass(frozen=True, kw_only=True)
class CreateAccount(Command[EmailAccount]):
    tenant_id: str
    settings: AccountSettings
    passwords: Passwords


class CreateAccountHandler:
    def __init__(self, accounts: AccountRepository, vault: Vault, ids: IdGenerator, clock: Clock) -> None:
        self._accounts = accounts
        self._vault = vault
        self._ids = ids
        self._clock = clock

    async def handle(self, command: CreateAccount) -> EmailAccount:
        account = EmailAccount.create(
            id=self._ids.new_id(), tenant_id=command.tenant_id, settings=command.settings, now=self._clock.now()
        )
        if len(await self._accounts.of_tenant(command.tenant_id)) >= ACCOUNTS_MAX:
            raise InvalidAccountError('limit')
        if await self._accounts.address_taken(command.tenant_id, account.address):
            raise AccountAddressTakenError()
        await self._accounts.save(account)
        await self._vault.store(account, command.passwords)
        return account


@dataclass(frozen=True, kw_only=True)
class UpdateAccount(Command[EmailAccount]):
    tenant_id: str
    account_id: str
    settings: AccountSettings
    passwords: Passwords


class UpdateAccountHandler:
    def __init__(self, accounts: AccountRepository, vault: Vault, clock: Clock) -> None:
        self._accounts = accounts
        self._vault = vault
        self._clock = clock

    async def handle(self, command: UpdateAccount) -> EmailAccount:
        account = await self._accounts.find(command.tenant_id, command.account_id)
        if account is None:
            raise AccountNotFoundError()
        account.change(command.settings, self._clock.now())
        if await self._accounts.address_taken(command.tenant_id, account.address, except_id=account.id):
            raise AccountAddressTakenError()
        await self._accounts.save(account)
        await self._vault.store(account, command.passwords)
        return account


@dataclass(frozen=True, kw_only=True)
class DeleteAccount(Command[EmailAccount]):
    tenant_id: str
    account_id: str


class DeleteAccountHandler:
    def __init__(self, accounts: AccountRepository) -> None:
        self._accounts = accounts

    async def handle(self, command: DeleteAccount) -> EmailAccount:
        account = await self._accounts.find(command.tenant_id, command.account_id)
        if account is None:
            raise AccountNotFoundError()
        await self._accounts.delete(command.tenant_id, account.id)
        return account


@dataclass(frozen=True)
class ProbeResult:
    imap: str | None
    """None if it worked, else what the server said."""
    smtp: str | None


@dataclass(frozen=True, kw_only=True)
class TestAccount(Command[ProbeResult]):
    """Logs in to both servers (the test button when setting up an account)."""

    tenant_id: str
    account_id: str


class TestAccountHandler:
    def __init__(self, accounts: AccountRepository, vault: Vault, mailbox: Mailbox, outbox: Outbox) -> None:
        self._accounts = accounts
        self._vault = vault
        self._mailbox = mailbox
        self._outbox = outbox

    async def handle(self, command: TestAccount) -> ProbeResult:
        account = await self._accounts.find(command.tenant_id, command.account_id)
        if account is None:
            raise AccountNotFoundError()
        imap = await self._try(self._mailbox.probe, account, 'imap')
        smtp = await self._try(self._outbox.probe, account, 'smtp')
        return ProbeResult(imap=imap, smtp=smtp)

    async def _try(
        self, probe: Callable[[EmailAccount, Credential], Awaitable[None]], account: EmailAccount, kind: ServerKind
    ) -> str | None:
        try:
            await probe(account, await self._vault.credential(account, kind))
        except MailboxError as error:
            return str(error) or 'failed'
        return None
