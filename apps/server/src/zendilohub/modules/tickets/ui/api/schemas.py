from collections.abc import Mapping
from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from zendilohub.core.contracts import ContactCard
from zendilohub.core.domain.queue_rights import QueueRight, ordered
from zendilohub.core.http.ids import Id

from ...application.commands.tickets import BulkResult, FirstMessage
from ...application.queries.tickets import TicketDetail, TicketWithRights
from ...domain.models.history import HistoryAction, HistoryEntry
from ...domain.models.link import LinkKind
from ...domain.models.message import AuthorKind, Direction, Message, MessageKind
from ...domain.models.ticket import SUBJECT_MAX, TAGS_MAX, Channel, Priority, Ticket, TicketState
from ...domain.models.time_entry import MINUTES_MAX, TimeEntry

type SettableState = Literal['new', 'open', 'pending_reminder', 'pending_close', 'closed']
BODY_LIMIT = 200_000


class Request(BaseModel):
    model_config = ConfigDict(extra='forbid')


class CustomerRequest(Request):
    """An existing contact (`id`), or one found or made by `email` or `phone`."""

    id: Id | None = None
    email: str | None = Field(default=None, max_length=254)
    name: str = Field(default='', max_length=200)
    phone: str | None = Field(default=None, max_length=40)


class CreateTicketRequest(Request):
    queue_id: Id
    subject: str = Field(max_length=SUBJECT_MAX)
    body: str = Field(max_length=BODY_LIMIT)
    first: FirstMessage = 'customer'
    """What the ticket starts with: what the customer said, a reply to them, or an internal note."""
    customer: CustomerRequest | None = None
    channel: Literal['web', 'phone', 'api'] = 'web'
    priority: Priority = 'normal'
    tags: list[str] = Field(default_factory=list, max_length=TAGS_MAX)
    owner_id: Id | None = None
    state: SettableState | None = None
    pending_until: AwareDatetime | None = None
    time_minutes: int | None = Field(default=None, ge=1, le=MINUTES_MAX)


class TicketChangesRequest(Request):
    """Only the fields sent change; `null` clears owner, responsible, customer or the pending date."""

    subject: str | None = Field(default=None, max_length=SUBJECT_MAX)
    state: SettableState | None = None
    pending_until: AwareDatetime | None = None
    priority: Priority | None = None
    owner_id: Id | None = None
    responsible_id: Id | None = None
    queue_id: Id | None = None
    tags: list[str] | None = Field(default=None, max_length=TAGS_MAX)
    customer_id: Id | None = None


class BulkRequest(Request):
    ticket_ids: list[Id] = Field(min_length=1, max_length=200)
    state: SettableState | None = None
    pending_until: AwareDatetime | None = None
    priority: Priority | None = None
    owner_id: Id | None = None
    queue_id: Id | None = None
    add_tags: list[str] = Field(default_factory=list, max_length=TAGS_MAX)


class MessageRequest(Request):
    kind: MessageKind
    body: str = Field(max_length=BODY_LIMIT)
    direction: Direction = 'out'
    """`in` writes down what the customer said (e.g. on the phone)."""
    state: SettableState | None = None
    pending_until: AwareDatetime | None = None
    time_minutes: int | None = Field(default=None, ge=1, le=MINUTES_MAX)
    mentions: list[Id] = Field(default_factory=list, max_length=20)
    """Members who start watching the ticket."""


class LinkRequest(Request):
    number: int = Field(ge=1)
    kind: LinkKind = 'related'


class MergeRequest(Request):
    number: int = Field(ge=1)
    """The ticket this one goes into."""


class SplitRequest(Request):
    message_id: Id
    subject: str | None = Field(default=None, max_length=SUBJECT_MAX)


class TimeRequest(Request):
    minutes: int = Field(ge=1, le=MINUTES_MAX)


class CustomerCardResponse(BaseModel):
    id: str
    name: str
    email: str | None
    phone: str | None
    company_id: str | None
    company_name: str | None

    @classmethod
    def of(cls, card: ContactCard) -> CustomerCardResponse:
        return cls(**vars(card))


class TicketResponse(BaseModel):
    id: str
    number: int
    subject: str
    queue_id: str
    state: TicketState
    priority: Priority
    channel: Channel
    customer: CustomerCardResponse | None
    owner_id: str | None
    responsible_id: str | None
    tags: list[str]
    pending_until: datetime | None
    merged_into_id: str | None
    created_at: datetime
    updated_at: datetime
    first_response_at: datetime | None
    closed_at: datetime | None
    last_message_at: datetime | None
    rights: list[QueueRight]
    """What the caller may do with the ticket (their rights in its queue)."""

    @classmethod
    def of(cls, ticket: Ticket, rights: frozenset[QueueRight], cards: Mapping[str, ContactCard]) -> TicketResponse:
        card = cards.get(ticket.customer_id) if ticket.customer_id else None
        return cls(
            id=ticket.id,
            number=ticket.number,
            subject=ticket.subject,
            queue_id=ticket.queue_id,
            state=ticket.state,
            priority=ticket.priority,
            channel=ticket.channel,
            customer=CustomerCardResponse.of(card) if card else None,
            owner_id=ticket.owner_id,
            responsible_id=ticket.responsible_id,
            tags=list(ticket.tags),
            pending_until=ticket.pending_until,
            merged_into_id=ticket.merged_into_id,
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
            first_response_at=ticket.first_response_at,
            closed_at=ticket.closed_at,
            last_message_at=ticket.last_message_at,
            rights=list(ordered(rights)),
        )


class TicketPageResponse(BaseModel):
    items: list[TicketResponse]
    total: int

    @classmethod
    def of(cls, items: list[TicketWithRights], total: int, cards: Mapping[str, ContactCard]) -> TicketPageResponse:
        return cls(items=[TicketResponse.of(each.ticket, each.rights, cards) for each in items], total=total)


class LinkedTicketResponse(BaseModel):
    id: str
    number: int
    subject: str
    state: TicketState
    kind: LinkKind
    """What the other ticket is to this one."""


class TicketRef(BaseModel):
    id: str
    number: int


class TicketDetailResponse(TicketResponse):
    watchers: list[str]
    watching: bool
    links: list[LinkedTicketResponse]
    time_minutes: int
    merged_into: TicketRef | None

    @classmethod
    def of_detail(cls, detail: TicketDetail, user_id: str, cards: Mapping[str, ContactCard]) -> TicketDetailResponse:
        base = TicketResponse.of(detail.ticket, detail.rights, cards)
        return cls(
            **base.model_dump(exclude={'customer'}),
            customer=base.customer,
            watchers=list(detail.watchers),
            watching=user_id in detail.watchers,
            links=[
                LinkedTicketResponse(
                    id=each.ticket.id,
                    number=each.ticket.number,
                    subject=each.ticket.subject,
                    state=each.ticket.state,
                    kind=each.link.kind,
                )
                for each in detail.links
            ],
            time_minutes=detail.time_minutes,
            merged_into=TicketRef(id=detail.merged_into.id, number=detail.merged_into.number)
            if detail.merged_into
            else None,
        )


class MessageResponse(BaseModel):
    id: str
    ticket_id: str
    kind: MessageKind
    direction: Direction
    author_kind: AuthorKind
    author_id: str | None
    author_name: str
    body: str
    body_html: str | None
    subject: str | None
    from_address: str | None
    to_addresses: list[str]
    cc_addresses: list[str]
    created_at: datetime

    @classmethod
    def of(cls, message: Message) -> MessageResponse:
        return cls(
            id=message.id,
            ticket_id=message.ticket_id,
            kind=message.kind,
            direction=message.direction,
            author_kind=message.author_kind,
            author_id=message.author_id,
            author_name=message.author_name,
            body=message.body,
            body_html=message.body_html,
            subject=message.subject,
            from_address=message.from_address,
            to_addresses=list(message.to_addresses),
            cc_addresses=list(message.cc_addresses),
            created_at=message.created_at,
        )


class HistoryEntryResponse(BaseModel):
    id: str
    actor_id: str | None
    actor_name: str
    action: HistoryAction
    field: str | None
    old: str | None
    new: str | None
    created_at: datetime

    @classmethod
    def of(cls, entry: HistoryEntry) -> HistoryEntryResponse:
        return cls(
            id=entry.id,
            actor_id=entry.actor_id,
            actor_name=entry.actor_name,
            action=entry.action,
            field=entry.field,
            old=entry.old,
            new=entry.new,
            created_at=entry.created_at,
        )


class TimeEntryResponse(BaseModel):
    id: str
    user_id: str
    minutes: int
    message_id: str | None
    created_at: datetime

    @classmethod
    def of(cls, entry: TimeEntry) -> TimeEntryResponse:
        return cls(
            id=entry.id,
            user_id=entry.user_id,
            minutes=entry.minutes,
            message_id=entry.message_id,
            created_at=entry.created_at,
        )


class TicketCountsResponse(BaseModel):
    mine: int
    unassigned: int
    due: int
    open: int
    watching: int


class BulkResponse(BaseModel):
    changed: list[str]
    failed: dict[str, str]
    """Ticket id → error code, for tickets the caller may not change like this."""

    @classmethod
    def of(cls, result: BulkResult) -> BulkResponse:
        return cls(changed=result.changed, failed=result.failed)
