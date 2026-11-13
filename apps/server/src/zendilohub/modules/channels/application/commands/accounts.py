from collections.abc import Awaitable, Callable
from dataclasses import dataclass

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
from ...domain.ports.repositories import AccountRepository
from ...domain.ports.services import Mailbox, MailboxError, Outbox


class Vault:
    """The accounts' passwords, sealed at rest."""

    def __init__(self, accounts: AccountRepository, cipher: Cipher) -> None:
        self._accounts = accounts
        self._cipher = cipher

    async def store(self, account: EmailAccount, passwords: Passwords) -> None:
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
        imap = await self._try(self._mailbox.probe, account, await self._vault.password(account, 'imap'))
        smtp = await self._try(self._outbox.probe, account, await self._vault.password(account, 'smtp'))
        return ProbeResult(imap=imap, smtp=smtp)

    @staticmethod
    async def _try(
        probe: Callable[[EmailAccount, str], Awaitable[None]], account: EmailAccount, password: str
    ) -> str | None:
        try:
            await probe(account, password)
        except MailboxError as error:
            return str(error) or 'failed'
        return None
