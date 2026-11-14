"""Files the modules hand each other: attachments of e-mails and of the customer portal."""

from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class FileData:
    """A whole file in memory (at most the upload limit)."""

    filename: str
    content_type: str
    content: bytes
    content_id: str | None = None
    """The `Content-ID` of an image an HTML e-mail shows inline."""


@dataclass(frozen=True, kw_only=True)
class FileInfo:
    """What a list of attachments shows: no content."""

    id: str
    filename: str
    content_type: str
    size: int
