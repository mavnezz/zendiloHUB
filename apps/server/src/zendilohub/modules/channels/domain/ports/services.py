from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from zendilohub.core.domain.files import FileData
from zendilohub.core.domain.inbox import InboundEmail, OutgoingEmail, ReceivedTicket

from ..models.account import EmailAccount, Provider
from ..models.smime import CertificateInfo, Seal, SigningKey, Verification


@dataclass(frozen=True)
class Fetched:
    uid_validity: int
    messages: Sequence[tuple[int, bytes]]
    """New mails as (UID, raw message), oldest first."""


class MailboxError(Exception):
    """The mail server refused or could not be reached; the message says why (shown to admins)."""


@dataclass(frozen=True)
class Credential:
    """How to log in to a mail server: a password, or an OAuth access token (SASL XOAUTH2)."""

    secret: str
    oauth: bool = False


class Mailbox(Protocol):
    """Reads an account's mailbox by IMAP."""

    async def fetch(
        self, account: EmailAccount, credential: Credential, *, after_uid: int, uid_validity: int | None, limit: int
    ) -> Fetched:
        """Mails with a UID above `after_uid`; all new ones when the mailbox's UIDVALIDITY changed. Marks them seen."""
        ...

    async def probe(self, account: EmailAccount, credential: Credential) -> None:
        """Logs in and opens the folder; raises MailboxError."""
        ...


@dataclass(frozen=True, kw_only=True)
class OutgoingMail:
    sender: str
    to: tuple[str, ...]
    subject: str
    text: str
    message_id: str
    in_reply_to: str | None = None
    references: tuple[str, ...] = ()
    automatic: bool = False
    """Auto replies say so (`Auto-Submitted`), so other robots do not answer them."""
    attachments: tuple[FileData, ...] = ()
    seal: Seal | None = None
    """S/MIME: signed and/or encrypted when set."""


class Outbox(Protocol):
    """Sends mail by an account's SMTP server."""

    async def send(self, account: EmailAccount, credential: Credential, mail: OutgoingMail) -> None:
        """Raises MailboxError."""
        ...

    async def probe(self, account: EmailAccount, credential: Credential) -> None: ...


class HtmlCleaner(Protocol):
    def clean(self, html: str) -> str:
        """Only harmless markup stays: no scripts, no styles that load anything, no external images."""
        ...


class Tickets(Protocol):
    """The tickets module (its `TicketInbox` contract)."""

    async def thread(self, tenant_id: str, email_ids: list[str], number: int | None) -> str | None: ...

    async def receive(self, email: InboundEmail) -> ReceivedTicket: ...

    async def outgoing(self, tenant_id: str, message_id: str) -> OutgoingEmail | None: ...

    async def mark_sent(
        self, tenant_id: str, message_id: str, *, email_message_id: str, from_address: str, to: tuple[str, ...]
    ) -> None: ...

    async def subject_prefix(self, tenant_id: str) -> str:
        """What stands before the number in subjects: `#` for `[#1001]`."""
        ...


class Names(Protocol):
    """Names for placeholders: the organization's, a queue's, a member's e-mail address."""

    async def organization(self, tenant_id: str) -> str: ...

    async def queue(self, tenant_id: str, queue_id: str) -> str | None: ...

    async def member_email(self, tenant_id: str, user_id: str) -> str | None: ...


@dataclass(frozen=True, kw_only=True)
class TokenGrant:
    access_token: str
    expires_in: int
    """Seconds."""
    refresh_token: str | None
    """None: the provider keeps the one it gave before."""
    address: str | None = None
    """The mailbox's address (from the ID token); only when a code was exchanged."""


class OAuthError(Exception):
    """The provider refused; `code` is its OAuth error (e.g. `invalid_grant`) or ours (`unreachable`, `no_address`)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class OAuthProviders(Protocol):
    """The mail providers' OAuth endpoints (authorization code flow with PKCE)."""

    def configured(self) -> tuple[Provider, ...]:
        """The providers the instance has app credentials for."""
        ...

    def authorize_url(self, provider: Provider, *, state: str, challenge: str, redirect_uri: str) -> str: ...

    async def exchange(self, provider: Provider, *, code: str, verifier: str, redirect_uri: str) -> TokenGrant:
        """Raises OAuthError."""
        ...

    async def refresh(self, provider: Provider, refresh_token: str) -> TokenGrant:
        """Raises OAuthError; `invalid_grant` means the connection is gone for good."""
        ...


class SmimeError(Exception):
    """A certificate, key or S/MIME structure could not be read or used; `reason` says which."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class SmimeEngine(Protocol):
    """The cryptography of S/MIME (CMS, RFC 5652): certificates, keys, signing, encryption and their reverse."""

    def read_certificate(self, data: bytes) -> CertificateInfo:
        """PEM or DER; raises SmimeError."""
        ...

    def read_pkcs12(self, data: bytes, password: str) -> tuple[CertificateInfo, str]:
        """A PKCS #12 file (.p12, .pfx): the certificate and its private key (PEM); raises SmimeError."""
        ...

    def read_key(self, data: bytes, password: str, certificate: CertificateInfo) -> str:
        """A private key (PEM or DER) that must belong to `certificate`, as PEM; raises SmimeError."""
        ...

    def sign(self, content: bytes, key: SigningKey) -> bytes:
        """A detached signature (DER) over `content`, which is canonical already."""
        ...

    def encrypt(self, content: bytes, recipients: Sequence[str]) -> bytes:
        """Enveloped data (DER) for the PEM certificates `recipients`; raises SmimeError."""
        ...

    def kind(self, data: bytes) -> Literal['enveloped', 'signed'] | None: ...

    def decrypt(self, data: bytes, key: SigningKey) -> bytes | None:
        """None if the data is not for this key."""
        ...

    def verify(self, data: bytes, content: bytes | None, trusted: Sequence[str], now: datetime) -> Verification:
        """Checks a signature (DER): detached over `content`, or with the content inside. `trusted`: PEM certificates
        that count as trusted (authorities and certificates the organization added)."""
        ...
