from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formatdate

from zendilohub.modules.channels.domain.models.account import EmailAccount
from zendilohub.modules.channels.domain.ports.services import Fetched, MailboxError, OutgoingMail


@dataclass
class Mailbox:
    uid_validity: int = 1
    messages: list[tuple[int, bytes]] = field(default_factory=list)
    next_uid: int = 1


class FakeMailServer:
    """Mailboxes by address and the mails sent, for the channels module in tests."""

    def __init__(self) -> None:
        self.boxes: dict[str, Mailbox] = {}
        self.sent: list[tuple[str, OutgoingMail]] = []
        """(account address, mail)."""
        self.passwords: dict[str, str] = {}
        self.broken: dict[str, str] = {}
        """Address → the error its servers raise."""

    def deliver(self, address: str, raw: bytes) -> None:
        box = self.boxes.setdefault(address, Mailbox())
        box.messages.append((box.next_uid, raw))
        box.next_uid += 1

    def _check(self, account: EmailAccount, password: str) -> None:
        if account.address in self.broken:
            raise MailboxError(self.broken[account.address])
        expected = self.passwords.get(account.address)
        if expected is not None and password != expected:
            raise MailboxError('The server said: [AUTHENTICATIONFAILED] Invalid credentials')

    async def fetch(
        self, account: EmailAccount, password: str, *, after_uid: int, uid_validity: int | None, limit: int
    ) -> Fetched:
        self._check(account, password)
        box = self.boxes.setdefault(account.address, Mailbox())
        start = after_uid if uid_validity == box.uid_validity else 0
        return Fetched(box.uid_validity, [each for each in box.messages if each[0] > start][:limit])

    async def probe(self, account: EmailAccount, password: str) -> None:
        self._check(account, password)

    async def send(self, account: EmailAccount, password: str, mail: OutgoingMail) -> None:
        self._check(account, password)
        self.sent.append((account.address, mail))


def email(
    *,
    sender: str = 'Carl Customer <carl@customer.example>',
    to: str = 'support@acme.example',
    subject: str = 'Printer broken',
    text: str = 'It does not print.',
    message_id: str = '<m1@customer.example>',
    html: str | None = None,
    **headers: str,
) -> bytes:
    mail = EmailMessage()
    mail['From'] = sender
    mail['To'] = to
    mail['Subject'] = subject
    mail['Date'] = formatdate()
    if message_id:
        mail['Message-ID'] = message_id
    for name, value in headers.items():
        mail[name.replace('_', '-')] = value
    mail.set_content(text)
    if html is not None:
        mail.add_alternative(html, subtype='html')
    return mail.as_bytes()
