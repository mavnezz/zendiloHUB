import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime

FILENAME_MAX = 200
PER_MESSAGE = 20
"""Files one message may carry."""
INLINE_TYPES = frozenset({'image/png', 'image/jpeg', 'image/gif', 'image/webp'})
"""Shown in the browser; everything else downloads."""
DEFAULT_TYPE = 'application/octet-stream'

_TYPE = re.compile(r'^[a-z0-9][a-z0-9!#$&^_.+-]{0,63}/[a-z0-9][a-z0-9!#$&^_.+-]{0,126}$')
_UNSAFE = re.compile(r'[\x00-\x1f\x7f<>:"/\\|?*]')


def clean_filename(name: str) -> str:
    """The last part of a path, without control characters or characters file systems forbid; never empty."""
    name = unicodedata.normalize('NFC', name).replace('\\', '/').split('/')[-1]
    name = ' '.join(_UNSAFE.sub('_', name).split()).strip(' .')
    if len(name) > FILENAME_MAX:
        stem, dot, extension = name.rpartition('.')
        keep = extension if dot and 0 < len(extension) <= 16 else ''
        name = (stem if keep else name)[: FILENAME_MAX - len(keep) - 1].rstrip(' .') + (f'.{keep}' if keep else '')
    return name or 'file'


def clean_content_type(value: str | None) -> str:
    """A plain `type/subtype` in lower case (parameters dropped); unknown or odd types become octet-stream."""
    found = (value or '').split(';')[0].strip().lower()
    return found if _TYPE.match(found) else DEFAULT_TYPE


@dataclass(kw_only=True)
class Attachment:
    """A file of a message; `message_id` is None while it waits for the message being written."""

    id: str
    tenant_id: str
    ticket_id: str
    message_id: str | None
    filename: str
    content_type: str
    size: int
    sha256: str
    content_id: str | None = None
    created_by: str | None
    """The member who uploaded it; None for files of e-mails and of the portal."""
    created_at: datetime

    @property
    def inline(self) -> bool:
        return self.content_type in INLINE_TYPES
