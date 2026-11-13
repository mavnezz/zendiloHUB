"""IMAP and SMTP with the standard library, in a thread each (both are blocking)."""

import asyncio
import contextlib
import imaplib
import re
import smtplib
import socket
import ssl
from email.message import EmailMessage
from email.utils import formatdate

import nh3

from ..domain.models.account import EmailAccount, Server
from ..domain.ports.services import Fetched, MailboxError, OutgoingMail

TIMEOUT = 30
_UIDVALIDITY = re.compile(rb'UIDVALIDITY (\d+)')


def _context() -> ssl.SSLContext:
    return ssl.create_default_context()


class ImapMailbox:
    async def fetch(
        self, account: EmailAccount, password: str, *, after_uid: int, uid_validity: int | None, limit: int
    ) -> Fetched:
        return await asyncio.to_thread(self._fetch, account, password, after_uid, uid_validity, limit)

    async def probe(self, account: EmailAccount, password: str) -> None:
        await asyncio.to_thread(self._probe, account, password)

    def _probe(self, account: EmailAccount, password: str) -> None:
        with _imap(account.imap, password) as imap:
            _select(imap, account.folder)

    def _fetch(
        self, account: EmailAccount, password: str, after_uid: int, uid_validity: int | None, limit: int
    ) -> Fetched:
        with _imap(account.imap, password) as imap:
            validity = _select(imap, account.folder)
            start = after_uid + 1 if uid_validity == validity else 1
            status, data = imap.uid('SEARCH', f'UID {start}:*' if uid_validity == validity else 'UNSEEN')
            if status != 'OK':
                raise MailboxError('The mailbox could not be searched')
            uids = sorted(int(uid) for uid in (data[0] or b'').split() if int(uid) >= start)[:limit]
            messages: list[tuple[int, bytes]] = []
            for uid in uids:
                status, parts = imap.uid('FETCH', str(uid), '(BODY.PEEK[])')
                raw = next((part[1] for part in parts if isinstance(part, tuple)), None)
                if status == 'OK' and isinstance(raw, bytes):
                    messages.append((uid, raw))
                    imap.uid('STORE', str(uid), '+FLAGS', '(\\Seen)')
            return Fetched(uid_validity=validity, messages=messages)


class _Imap:
    def __init__(self, server: Server, password: str) -> None:
        self._server, self._password = server, password
        self._imap: imaplib.IMAP4 | None = None

    def __enter__(self) -> imaplib.IMAP4:
        server = self._server
        try:
            if server.security == 'ssl':
                imap: imaplib.IMAP4 = imaplib.IMAP4_SSL(
                    server.host, server.port, ssl_context=_context(), timeout=TIMEOUT
                )
            else:
                imap = imaplib.IMAP4(server.host, server.port, timeout=TIMEOUT)
                if server.security == 'starttls':
                    imap.starttls(ssl_context=_context())
            imap.login(server.username, self._password)
        except (OSError, imaplib.IMAP4.error, ssl.SSLError) as error:
            raise MailboxError(_reason(error)) from None
        self._imap = imap
        return imap

    def __exit__(self, *_: object) -> None:
        if self._imap is not None:
            with contextlib.suppress(OSError, imaplib.IMAP4.error):
                self._imap.logout()


def _imap(server: Server, password: str) -> _Imap:
    return _Imap(server, password)


def _select(imap: imaplib.IMAP4, folder: str) -> int:
    status, _ = imap.select(f'"{folder}"')
    if status != 'OK':
        raise MailboxError(f'The folder {folder} does not exist')
    responses = [item for item in imap.untagged_responses.get('OK', []) if isinstance(item, bytes)]
    found = _UIDVALIDITY.search(b' '.join(responses))
    _, data = imap.status(f'"{folder}"', '(UIDVALIDITY)')
    found = found or _UIDVALIDITY.search(data[0] or b'')
    return int(found.group(1)) if found else 0


def _reason(error: BaseException) -> str:
    if isinstance(error, socket.gaierror):
        return 'The server name is unknown'
    if isinstance(error, (TimeoutError, socket.timeout)):
        return 'The server did not answer'
    if isinstance(error, ConnectionRefusedError):
        return 'The server refused the connection (port?)'
    if isinstance(error, ssl.SSLError):
        return f'Encryption failed: {error.reason or error}'
    text = error.args[0] if error.args else str(error)
    if isinstance(text, bytes):
        text = text.decode('utf-8', 'replace')
    return f'The server said: {text}'[:300]


class SmtpOutbox:
    async def send(self, account: EmailAccount, password: str, mail: OutgoingMail) -> None:
        await asyncio.to_thread(self._send, account, password, _compose(mail))

    async def probe(self, account: EmailAccount, password: str) -> None:
        await asyncio.to_thread(self._send, account, password, None)

    def _send(self, account: EmailAccount, password: str, mail: EmailMessage | None) -> None:
        server = account.smtp
        try:
            smtp: smtplib.SMTP = (
                smtplib.SMTP_SSL(server.host, server.port, timeout=TIMEOUT, context=_context())
                if server.security == 'ssl'
                else smtplib.SMTP(server.host, server.port, timeout=TIMEOUT)
            )
            with smtp:
                if server.security == 'starttls':
                    smtp.starttls(context=_context())
                if server.username:
                    smtp.login(server.username, password)
                if mail is not None:
                    smtp.send_message(mail)
        except (OSError, smtplib.SMTPException, ssl.SSLError) as error:
            raise MailboxError(_reason(error)) from None


def _compose(mail: OutgoingMail) -> EmailMessage:
    message = EmailMessage()
    message['From'] = mail.sender
    message['To'] = ', '.join(mail.to)
    message['Subject'] = mail.subject
    message['Date'] = formatdate(localtime=False)
    message['Message-ID'] = mail.message_id
    if mail.in_reply_to:
        message['In-Reply-To'] = mail.in_reply_to
    if mail.references:
        message['References'] = ' '.join(mail.references)
    if mail.automatic:
        message['Auto-Submitted'] = 'auto-replied'
        message['X-Auto-Response-Suppress'] = 'All'
    message.set_content(mail.text)
    return message


class Nh3Cleaner:
    """Allows text formatting, links and tables; no scripts, styles, forms or images from elsewhere."""

    _TAGS = frozenset(
        {
            'a',
            'b',
            'blockquote',
            'br',
            'code',
            'div',
            'em',
            'h1',
            'h2',
            'h3',
            'h4',
            'hr',
            'i',
            'li',
            'ol',
            'p',
            'pre',
            'span',
            'strong',
            'table',
            'tbody',
            'td',
            'th',
            'thead',
            'tr',
            'u',
            'ul',
        }
    )

    def clean(self, html: str) -> str:
        return nh3.clean(
            html,
            tags=set(self._TAGS),
            attributes={'a': {'href', 'title'}, 'td': {'colspan', 'rowspan'}, 'th': {'colspan', 'rowspan'}},
            url_schemes={'http', 'https', 'mailto'},
            link_rel='noopener noreferrer nofollow',
        ).strip()
