"""Reading received e-mails with the standard library: headers, text, threading and whether a robot wrote them."""

import re
from dataclasses import dataclass
from email import message_from_bytes, policy
from email.message import EmailMessage
from email.utils import getaddresses, parseaddr
from html.parser import HTMLParser

DEFAULT_PREFIX = '#'
_NUMBER = re.compile(r'\[#(\d{1,15})\]')


def _tags(prefixes: tuple[str, ...]) -> re.Pattern[str]:
    """`[<prefix><number>]` for any of the prefixes (the organization's and the default `#` of older mails)."""
    known = sorted({DEFAULT_PREFIX, *(each for each in prefixes if each)}, key=len, reverse=True)
    return re.compile(rf'\[(?:{"|".join(re.escape(each) for each in known)})(\d{{1,15}})\]')


_MESSAGE_ID = re.compile(r'<[^<>\s]+>')


@dataclass(frozen=True, kw_only=True)
class MailFile:
    filename: str
    content_type: str
    content: bytes
    content_id: str | None


@dataclass(frozen=True, kw_only=True)
class ParsedEmail:
    message_id: str | None
    in_reply_to: str | None
    references: tuple[str, ...]
    from_address: str
    from_name: str
    to: tuple[str, ...]
    cc: tuple[str, ...]
    subject: str
    text: str
    html: str | None
    headers: dict[str, str]
    """Lower-case header names (the first value of each), for filters."""
    automatic: bool
    """An auto reply, a bounce or a mass mail: never answered automatically."""
    files: tuple[MailFile, ...] = ()
    """Attachments and inline images, in the order of the mail."""

    @property
    def thread_ids(self) -> list[str]:
        ids = [*self.references, *([self.in_reply_to] if self.in_reply_to else [])]
        return list(dict.fromkeys(reversed(ids)))

    @property
    def ticket_number(self) -> int | None:
        return self.number_tagged(DEFAULT_PREFIX)

    def number_tagged(self, prefix: str) -> int | None:
        """The last `[<prefix>1001]` (or `[#1001]`) in the subject."""
        found = (_NUMBER if prefix == DEFAULT_PREFIX else _tags((prefix,))).findall(self.subject)
        return int(found[-1]) if found else None


def parse_email(raw: bytes) -> ParsedEmail:
    mail = message_from_bytes(raw, policy=policy.default)
    assert isinstance(mail, EmailMessage)
    name, address = parseaddr(str(mail.get('From', '')))
    text, html, bodies = _bodies(mail)
    headers = {key.lower(): str(value) for key, value in reversed(list(mail.items()))}
    return ParsedEmail(
        message_id=_one_id(mail.get('Message-ID')),
        in_reply_to=_one_id(mail.get('In-Reply-To')),
        references=tuple(_MESSAGE_ID.findall(str(mail.get('References', '')))),
        from_address=address.strip().lower(),
        from_name=name.strip(),
        to=_addresses(mail, 'To'),
        cc=_addresses(mail, 'Cc'),
        subject=' '.join(str(mail.get('Subject', '')).split()),
        text=text if text.strip() else html_to_text(html or ''),
        html=html,
        headers=headers,
        automatic=_automatic(headers, address),
        files=tuple(_files(mail, bodies)),
    )


def _one_id(value: object) -> str | None:
    found = _MESSAGE_ID.findall(str(value or ''))
    return found[0] if found else None


def _addresses(mail: EmailMessage, header: str) -> tuple[str, ...]:
    values = [str(value) for value in mail.get_all(header, [])]
    return tuple(address.strip().lower() for _, address in getaddresses(values) if '@' in address)


def _bodies(mail: EmailMessage) -> tuple[str, str | None, list[EmailMessage]]:
    plain = mail.get_body(preferencelist=('plain',))
    rich = mail.get_body(preferencelist=('html',))
    text = _content(plain) if isinstance(plain, EmailMessage) else ''
    html = _content(rich) if isinstance(rich, EmailMessage) else None
    bodies = [part for part in (plain, rich) if isinstance(part, EmailMessage)]
    return text.replace('\r\n', '\n').strip(), html, bodies


FILES_MAX = 50


def _files(mail: EmailMessage, bodies: list[EmailMessage]) -> list[MailFile]:
    """Parts with a file name, attachments and inline images; not the text the mail shows."""
    found: list[MailFile] = []
    for part in mail.walk():
        if part.is_multipart() or any(part is body for body in bodies) or not isinstance(part, EmailMessage):
            continue
        filename = part.get_filename()
        content_id = _one_id(part.get('Content-ID'))
        is_file = (
            filename is not None
            or part.get_content_disposition() == 'attachment'
            or (content_id is not None and part.get_content_maintype() == 'image')
        )
        if not is_file:
            continue
        payload = part.get_payload(decode=True)
        if not isinstance(payload, bytes):
            continue
        found.append(
            MailFile(
                filename=filename or _name_for(part),
                content_type=part.get_content_type(),
                content=payload,
                content_id=content_id,
            )
        )
        if len(found) >= FILES_MAX:
            break
    return found


def _name_for(part: EmailMessage) -> str:
    subtype = part.get_content_subtype()
    return f'{part.get_content_maintype()}.{subtype}' if subtype.isalnum() else 'file'


def _content(part: EmailMessage) -> str:
    try:
        return str(part.get_content())
    except LookupError, ValueError:
        payload = part.get_payload(decode=True)
        return payload.decode('utf-8', 'replace') if isinstance(payload, bytes) else ''


_AUTOMATIC_SENDERS = ('mailer-daemon@', 'postmaster@', 'noreply@', 'no-reply@', 'donotreply@')


def _automatic(headers: dict[str, str], address: str) -> bool:
    submitted = headers.get('auto-submitted', 'no').strip().lower()
    precedence = headers.get('precedence', '').strip().lower()
    return (
        submitted != 'no'
        or precedence in ('bulk', 'junk', 'list', 'auto_reply')
        or any(name in headers for name in ('x-autoreply', 'x-autorespond', 'list-id', 'list-unsubscribe'))
        or 'oof' in headers.get('x-auto-response-suppress', '').lower()
        or headers.get('return-path', '').strip() == '<>'
        or address.lower().startswith(_AUTOMATIC_SENDERS)
    )


class _TextOfHtml(HTMLParser):
    _BLOCKS = frozenset({'p', 'div', 'br', 'li', 'tr', 'h1', 'h2', 'h3', 'h4', 'blockquote', 'table'})

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ('script', 'style', 'head'):
            self._skip += 1
        elif tag in self._BLOCKS:
            self.parts.append('\n')

    def handle_endtag(self, tag: str) -> None:
        if tag in ('script', 'style', 'head'):
            self._skip = max(0, self._skip - 1)
        elif tag in self._BLOCKS:
            self.parts.append('\n')

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _TextOfHtml()
    parser.feed(html)
    text = ''.join(parser.parts)
    lines = [' '.join(line.split()) for line in text.splitlines()]
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).strip()


def reply_subject(subject: str, number: int, prefix: str = DEFAULT_PREFIX) -> str:
    """`Re: Printer broken [#1001]`: the number lets answers find the ticket even without their headers."""
    base = _tags((prefix,)).sub('', subject).strip()
    base = re.sub(r'^((re|aw|fw|fwd|wg)\s*:\s*)+', '', base, flags=re.IGNORECASE).strip()
    return f'Re: {base} {tagged(number, prefix)}'


def tagged(number: int, prefix: str = DEFAULT_PREFIX) -> str:
    return f'[{prefix}{number}]'
