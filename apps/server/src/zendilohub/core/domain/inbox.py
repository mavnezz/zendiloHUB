"""What the tickets and channels modules hand each other about e-mails (see the `TicketInbox` contract)."""

from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class InboundEmail:
    """A received e-mail for the tickets module: a new ticket in `queue_id`, or a message in `ticket_id`."""

    tenant_id: str
    queue_id: str
    ticket_id: str | None
    from_address: str
    from_name: str
    subject: str
    body: str
    body_html: str | None
    email_message_id: str | None
    in_reply_to: str | None
    references: tuple[str, ...]
    to_addresses: tuple[str, ...]
    cc_addresses: tuple[str, ...]
    priority: str | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class ReceivedTicket:
    ticket_id: str
    number: int
    created: bool
    customer_id: str | None


@dataclass(frozen=True, kw_only=True)
class OutgoingEmail:
    """A reply of the team, to be sent to the customer."""

    ticket_id: str
    number: int
    subject: str
    queue_id: str
    customer_email: str | None
    customer_name: str
    body: str
    author_id: str | None
    references: tuple[str, ...]
    """The e-mail ids of the ticket's earlier messages, oldest first (the last one is `In-Reply-To`)."""
