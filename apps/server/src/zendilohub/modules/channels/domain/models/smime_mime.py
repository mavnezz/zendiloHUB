"""The MIME side of S/MIME (RFC 8551), byte-exact: a signature covers the bytes as sent, so nothing may re-encode them."""

import base64
import re
import secrets
from dataclasses import dataclass
from email import message_from_bytes, policy
from email.message import EmailMessage
from email.utils import parseaddr
from typing import Literal

_HEADER_END = re.compile(rb'\r?\n\r?\n')
_HEADER_LINE = re.compile(rb'^[!-9;-~]+:')
_CONTENT_HEADERS = (b'content-', b'mime-version')


def canonical(data: bytes) -> bytes:
    """Line ends as CRLF: the form signatures are made over (RFC 8551, 3.1.1)."""
    return re.sub(rb'\r?\n', b'\r\n', data)


def _base64_lines(data: bytes) -> bytes:
    encoded = base64.b64encode(data)
    return b'\r\n'.join(encoded[index : index + 76] for index in range(0, len(encoded), 76)) + b'\r\n'


def signed_entity(content: bytes, signature: bytes, *, boundary: str | None = None) -> bytes:
    """multipart/signed: `content` exactly as signed, then the detached signature (DER)."""
    boundary = boundary or f'=_smime_{secrets.token_hex(12)}'
    return b''.join(
        (
            b'Content-Type: multipart/signed; protocol="application/pkcs7-signature"; micalg=sha-256;\r\n',
            f' boundary="{boundary}"\r\n\r\n'.encode(),
            b'This is a cryptographically signed message in MIME format.\r\n\r\n',
            f'--{boundary}\r\n'.encode(),
            content,
            f'\r\n--{boundary}\r\n'.encode(),
            b'Content-Type: application/pkcs7-signature; name="smime.p7s"\r\n',
            b'Content-Transfer-Encoding: base64\r\n',
            b'Content-Disposition: attachment; filename="smime.p7s"\r\n\r\n',
            _base64_lines(signature),
            f'\r\n--{boundary}--\r\n'.encode(),
        )
    )


def enveloped_entity(enveloped: bytes) -> bytes:
    """application/pkcs7-mime with the encrypted content (DER)."""
    return b''.join(
        (
            b'Content-Type: application/pkcs7-mime; smime-type=enveloped-data; name="smime.p7m"\r\n',
            b'Content-Transfer-Encoding: base64\r\n',
            b'Content-Disposition: attachment; filename="smime.p7m"\r\n\r\n',
            _base64_lines(enveloped),
        )
    )


def split(raw: bytes) -> tuple[bytes, bytes]:
    """Header block (without the empty line) and body."""
    found = _HEADER_END.search(raw)
    if found is None:
        return raw, b''
    return raw[: found.start()], raw[found.end() :]


def _logical_headers(block: bytes) -> list[bytes]:
    headers: list[bytes] = []
    for line in re.split(rb'\r?\n', block):
        if line[:1] in (b' ', b'\t') and headers:
            headers[-1] += b'\r\n' + line
        elif line:
            headers.append(line)
    return headers


def with_headers(headers: bytes, entity: bytes) -> bytes:
    """A whole mail: the message headers (From, To, …) followed by the entity's own Content-* headers and body."""
    kept = [line for line in _logical_headers(headers) if not line.lower().startswith(_CONTENT_HEADERS)]
    if not _HEADER_LINE.match(entity):
        entity = b'Content-Type: text/plain; charset="utf-8"\r\n\r\n' + entity
    return b'\r\n'.join([*kept, b'MIME-Version: 1.0']) + b'\r\n' + entity


type LayerKind = Literal['pkcs7', 'signed']


@dataclass(frozen=True, kw_only=True)
class Layer:
    """The outermost S/MIME layer of a mail."""

    kind: LayerKind
    """`pkcs7`: application/pkcs7-mime (encrypted, or signed with the content inside); `signed`: multipart/signed."""
    data: bytes
    """The PKCS #7 structure (DER): the whole for `pkcs7`, the detached signature for `signed`."""
    content: bytes = b''
    """`signed` only: the signed entity, byte-exact and canonical."""


_PKCS7_MIME = ('application/pkcs7-mime', 'application/x-pkcs7-mime')
_PKCS7_SIGNATURE = ('application/pkcs7-signature', 'application/x-pkcs7-signature')


def _headers_of(block: bytes) -> EmailMessage:
    message = message_from_bytes(block + b'\r\n\r\n', policy=policy.default)
    assert isinstance(message, EmailMessage)
    return message


def _payload(part: bytes) -> bytes:
    message = message_from_bytes(part, policy=policy.default)
    payload = message.get_payload(decode=True)
    return payload if isinstance(payload, bytes) else b''


def layer(raw: bytes) -> Layer | None:
    """The S/MIME layer on the outside of `raw`, or None for a plain mail (or a signature that cannot be cut out)."""
    block, body = split(raw)
    headers = _headers_of(block)
    content_type = headers.get_content_type()
    if content_type in _PKCS7_MIME:
        data = _payload(raw)
        return Layer(kind='pkcs7', data=data) if data else None
    if content_type != 'multipart/signed':
        return None
    boundary = headers.get_param('boundary')
    if not isinstance(boundary, str) or not boundary:
        return None
    delimiter = re.compile(rb'(?:\A|\r?\n)--' + re.escape(boundary.encode()) + rb'(--)?[ \t]*(?:\r?\n|\Z)')
    marks = list(delimiter.finditer(body))
    if len(marks) < 3 or marks[0].group(1) or marks[1].group(1):
        return None
    content = body[marks[0].end() : marks[1].start()]
    signature_part = body[marks[1].end() : marks[2].start()]
    part_block, _ = split(signature_part)
    if _headers_of(part_block).get_content_type() not in _PKCS7_SIGNATURE:
        return None
    signature = _payload(signature_part)
    if not signature:
        return None
    return Layer(kind='signed', data=signature, content=canonical(content))


def replace_content(raw: bytes, entity: bytes) -> bytes:
    """`raw` with its content swapped for `entity` (decrypted, or the signed content): the headers stay."""
    block, _ = split(raw)
    return with_headers(block, entity)


def sender(raw: bytes) -> str:
    """The From address, lower-case: a signature must be by the sender to count."""
    block, _ = split(raw)
    return parseaddr(str(_headers_of(block).get('From', '')))[1].strip().lower()
