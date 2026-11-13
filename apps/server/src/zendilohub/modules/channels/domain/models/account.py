from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal, get_args

from zendilohub.core.domain.email_address import normalized_email

from ..exceptions import InvalidAccountError

type Security = Literal['ssl', 'starttls', 'none']
SECURITIES: tuple[Security, ...] = get_args(Security.__value__)
NAME_MAX = 80
HOST_MAX = 253
ACCOUNTS_MAX = 50


@dataclass(frozen=True, kw_only=True)
class Server:
    """Where to fetch (IMAP) or send (SMTP) mail; the password is kept apart, sealed."""

    host: str
    port: int
    security: Security
    username: str

    def checked(self, field: str) -> Server:
        host, username = self.host.strip().lower(), self.username.strip()
        if not host or len(host) > HOST_MAX or any(char.isspace() for char in host):
            raise InvalidAccountError(f'{field}.host')
        if not 1 <= self.port <= 65535:
            raise InvalidAccountError(f'{field}.port')
        if self.security not in SECURITIES:
            raise InvalidAccountError(f'{field}.security')
        if len(username) > 254:
            raise InvalidAccountError(f'{field}.username')
        return replace(self, host=host, username=username)


@dataclass(kw_only=True)
class EmailAccount:
    """
    A mailbox of the organization, e.g. support@: mail is fetched from it by IMAP into its queue, and the replies of
    queues that send with it go out by its SMTP server, from its address.
    """

    id: str
    tenant_id: str
    name: str
    address: str
    display_name: str
    queue_id: str
    imap: Server
    smtp: Server
    folder: str
    active: bool
    created_at: datetime
    updated_at: datetime
    last_uid: int = 0
    uid_validity: int | None = None
    last_fetch_at: datetime | None = None
    last_error: str | None = None
    failing_since: datetime | None = None

    @classmethod
    def create(cls, *, id: str, tenant_id: str, settings: AccountSettings, now: datetime) -> EmailAccount:
        account = cls(
            id=id,
            tenant_id=tenant_id,
            name='',
            address='',
            display_name='',
            queue_id=settings.queue_id,
            imap=settings.imap,
            smtp=settings.smtp,
            folder='INBOX',
            active=True,
            created_at=now,
            updated_at=now,
        )
        account.change(settings, now)
        return account

    def change(self, settings: AccountSettings, now: datetime) -> None:
        name, display_name, folder = (
            ' '.join(settings.name.split()),
            ' '.join(settings.display_name.split()),
            settings.folder.strip() or 'INBOX',
        )
        address = normalized_email(settings.address)
        if not 1 <= len(name) <= NAME_MAX:
            raise InvalidAccountError('name')
        if address is None:
            raise InvalidAccountError('address')
        if len(display_name) > NAME_MAX:
            raise InvalidAccountError('display_name')
        if len(folder) > 200:
            raise InvalidAccountError('folder')
        imap, smtp = settings.imap.checked('imap'), settings.smtp.checked('smtp')
        if imap != self.imap or address != self.address or folder != self.folder:
            # Another mailbox: start reading it from where it is now.
            self.uid_validity = None
        self.name, self.address, self.display_name, self.folder = name, address, display_name, folder
        self.queue_id, self.imap, self.smtp, self.active = settings.queue_id, imap, smtp, settings.active
        self.updated_at = now

    def fetched(self, *, uid_validity: int, last_uid: int, now: datetime) -> None:
        self.uid_validity, self.last_uid, self.last_fetch_at = uid_validity, last_uid, now
        self.last_error, self.failing_since = None, None

    def failed(self, error: str, now: datetime) -> None:
        self.last_error = error[:500]
        self.failing_since = self.failing_since or now
        self.last_fetch_at = now

    @property
    def sender(self) -> str:
        """`Name <address>` for the From header."""
        return f'{self.display_name} <{self.address}>' if self.display_name else self.address


@dataclass(frozen=True, kw_only=True)
class AccountSettings:
    name: str
    address: str
    display_name: str
    queue_id: str
    imap: Server
    smtp: Server
    folder: str = 'INBOX'
    active: bool = True


@dataclass(frozen=True)
class Passwords:
    """New passwords; None keeps the stored one."""

    imap: str | None = None
    smtp: str | None = None


type ServerKind = Literal['imap', 'smtp']


def sealing_context(account_id: str, kind: ServerKind) -> str:
    return f'channels.account.{account_id}.{kind}'
