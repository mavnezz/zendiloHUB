from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from ..exceptions import InvalidMessageError
from .attachment import Attachment

type MessageKind = Literal['public', 'internal']
"""Public messages go to (or came from) the customer; internal notes only the team sees."""
type Direction = Literal['in', 'out']
"""`in`: from the customer; `out`: from the team."""
type AuthorKind = Literal['agent', 'customer', 'system']

BODY_MAX = 200_000


@dataclass(kw_only=True)
class Message:
    """One message in a ticket. E-mail fields stay empty for messages written in the app."""

    id: str
    tenant_id: str
    ticket_id: str
    kind: MessageKind
    direction: Direction
    author_kind: AuthorKind
    author_id: str | None
    """A user for agents, a contact for customers."""
    author_name: str
    body: str
    """Plain text."""
    body_html: str | None = None
    """Cleaned HTML of received e-mails."""
    subject: str | None = None
    from_address: str | None = None
    to_addresses: tuple[str, ...] = ()
    cc_addresses: tuple[str, ...] = ()
    email_message_id: str | None = None
    in_reply_to: str | None = None
    references: tuple[str, ...] = field(default=())
    attachments: tuple[Attachment, ...] = ()
    """Filled when read; saved by the attachment repository."""
    created_at: datetime

    @classmethod
    def write(
        cls,
        *,
        id: str,
        tenant_id: str,
        ticket_id: str,
        kind: MessageKind,
        direction: Direction,
        author_kind: AuthorKind,
        author_id: str | None,
        author_name: str,
        body: str,
        now: datetime,
        with_files: bool = False,
        **email: object,
    ) -> Message:
        """`with_files`: files come along, so the text may be empty."""
        body = body.strip()
        if not body and not email.get('body_html') and not with_files:
            raise InvalidMessageError('body')
        if len(body) > BODY_MAX:
            raise InvalidMessageError('body')
        if kind == 'internal' and direction == 'in':
            raise InvalidMessageError('direction')
        return cls(
            id=id,
            tenant_id=tenant_id,
            ticket_id=ticket_id,
            kind=kind,
            direction=direction,
            author_kind=author_kind,
            author_id=author_id,
            author_name=author_name,
            body=body,
            created_at=now,
            **email,  # type: ignore[arg-type]
        )
