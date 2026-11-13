from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from zendilohub.core.domain.inbox import InboundEmail, OutgoingEmail, ReceivedTicket

from ..models.account import EmailAccount


@dataclass(frozen=True)
class Fetched:
    uid_validity: int
    messages: Sequence[tuple[int, bytes]]
    """New mails as (UID, raw message), oldest first."""


class MailboxError(Exception):
    """The mail server refused or could not be reached; the message says why (shown to admins)."""


class Mailbox(Protocol):
    """Reads an account's mailbox by IMAP."""

    async def fetch(
        self, account: EmailAccount, password: str, *, after_uid: int, uid_validity: int | None, limit: int
    ) -> Fetched:
        """Mails with a UID above `after_uid`; all new ones when the mailbox's UIDVALIDITY changed. Marks them seen."""
        ...

    async def probe(self, account: EmailAccount, password: str) -> None:
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


class Outbox(Protocol):
    """Sends mail by an account's SMTP server."""

    async def send(self, account: EmailAccount, password: str, mail: OutgoingMail) -> None:
        """Raises MailboxError."""
        ...

    async def probe(self, account: EmailAccount, password: str) -> None: ...


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


class Names(Protocol):
    """Names for placeholders: the organization's, a queue's, a member's e-mail address."""

    async def organization(self, tenant_id: str) -> str: ...

    async def queue(self, tenant_id: str, queue_id: str) -> str | None: ...

    async def member_email(self, tenant_id: str, user_id: str) -> str | None: ...
