from collections.abc import Iterable
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, Response

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.contracts import ContactCard, Contracts
from zendilohub.core.http.access import CurrentMember, CurrentPerson, Member, member_with
from zendilohub.core.http.audit import Unaudited, audited, note_audit
from zendilohub.core.http.ids import Id

from ...application.commands.assist import Assist, AssistantStatus
from ...application.commands.fields import (
    AddChecklistItem,
    BeHere,
    ChangeChecklistItem,
    Checklist,
    DeleteField,
    ListFields,
    SaveField,
)
from ...application.commands.messages import AddMessage
from ...application.commands.relations import (
    LinkTickets,
    MergeTicket,
    RecordTime,
    SplitTicket,
    UnlinkTickets,
    Watch,
)
from ...application.commands.tickets import (
    BulkUpdate,
    CreateTicket,
    CustomerRef,
    DeleteTicket,
    TicketChanges,
    UpdateTicket,
)
from ...application.queries.tickets import (
    Assignees,
    CountTickets,
    FindTicketByNumber,
    GetTicket,
    ListMessages,
    SearchTickets,
    SimilarTickets,
    TicketHistory,
    TicketTime,
)
from ...domain.models.actor import Actor
from ...domain.models.ticket import Priority, TicketState
from ...domain.models.views import TicketSort, TicketView
from .schemas import (
    AssistantResponse,
    AssistRequest,
    AssistResponse,
    BulkRequest,
    BulkResponse,
    ChecklistChangeRequest,
    ChecklistItemRequest,
    ChecklistItemResponse,
    CreateTicketRequest,
    FieldRequest,
    FieldResponse,
    HistoryEntryResponse,
    LinkRequest,
    MergeRequest,
    MessageRequest,
    MessageResponse,
    PresenceRequest,
    SplitRequest,
    TicketChangesRequest,
    TicketCountsResponse,
    TicketDetailResponse,
    TicketPageResponse,
    TicketResponse,
    TimeEntryResponse,
    TimeRequest,
    ViewerResponse,
)

FieldManager = Annotated[Member, member_with('queues.manage')]


def actor_of(member: Member) -> Actor:
    return Actor(
        user_id=member.user_id,
        name=member.principal.email,
        all_queues=member.can('queues.all'),
        person=member.acts_for_person,
    )


def ticket_routes(bus: CommandBus, contracts: Contracts) -> APIRouter:
    """
    Tickets. What the caller may do with one comes from their groups' rights in its queue (`rights` in every answer);
    tickets in queues they may not see do not exist for them. Changes are kept in each ticket's history, so only
    creating, merging and deleting go into the audit log.
    """
    router = APIRouter(prefix='/tenants/{tenant_id}', tags=['tickets'])

    async def cards(tenant_id: str, customer_ids: Iterable[str | None]) -> dict[str, ContactCard]:
        ids = sorted({each for each in customer_ids if each})
        return dict(await contracts.contacts.get().cards(tenant_id, ids)) if ids else {}

    async def detail(member: Member, ticket_id: str) -> TicketDetailResponse:
        found = await bus.query(GetTicket(tenant_id=member.tenant_id, actor=actor_of(member), ticket_id=ticket_id))
        return TicketDetailResponse.of_detail(
            found, member.user_id, await cards(member.tenant_id, [found.ticket.customer_id])
        )

    @router.get('/tickets')
    async def tickets(
        member: CurrentMember,
        view: TicketView = 'open',
        queue_id: Annotated[Id | None, Query()] = None,
        state: TicketState | None = None,
        priority: Priority | None = None,
        owner_id: Annotated[Id | None, Query()] = None,
        customer_id: Annotated[Id | None, Query()] = None,
        company_id: Annotated[Id | None, Query()] = None,
        ids: Annotated[list[Id] | None, Query(max_length=500)] = None,
        tag: Annotated[str | None, Query(max_length=50)] = None,
        q: Annotated[str, Query(max_length=200)] = '',
        sort: TicketSort = 'updated',
        descending: bool = True,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> TicketPageResponse:
        """
        A view of the inbox (`mine`, `unassigned`, `due`, `open`, `watching`, `closed`, `all`), narrowed by the
        filters; `q` searches number, subject and every message, `ids` keeps only these tickets.
        """
        page = await bus.query(
            SearchTickets(
                tenant_id=member.tenant_id,
                actor=actor_of(member),
                view=view,
                queue_id=queue_id,
                state=state,
                priority=priority,
                owner_id=owner_id,
                customer_id=customer_id,
                company_id=company_id,
                ticket_ids=tuple(ids) if ids is not None else None,
                tag=tag,
                query=q,
                sort=sort,
                descending=descending,
                offset=offset,
                limit=limit,
            )
        )
        found = await cards(member.tenant_id, [each.ticket.customer_id for each in page.items])
        return TicketPageResponse.of(list(page.items), page.total, found)

    @router.get('/tickets/counts')
    async def counts(member: CurrentMember) -> TicketCountsResponse:
        """How many tickets the views of the inbox have."""
        counted = await bus.query(CountTickets(tenant_id=member.tenant_id, actor=actor_of(member)))
        return TicketCountsResponse.model_validate(dict(counted))

    @router.post('/tickets', status_code=201, dependencies=[audited('ticket.created')])
    async def create(body: CreateTicketRequest, request: Request, member: CurrentMember) -> TicketDetailResponse:
        """A new ticket in a queue where the caller has `create` (and `reply` or `note` for what it starts with)."""
        customer = body.customer
        ticket = await bus.execute(
            CreateTicket(
                tenant_id=member.tenant_id,
                actor=actor_of(member),
                queue_id=body.queue_id,
                subject=body.subject,
                body=body.body,
                first=body.first,
                customer=CustomerRef(id=customer.id, email=customer.email, name=customer.name, phone=customer.phone)
                if customer
                else None,
                channel=body.channel,
                priority=body.priority,
                tags=tuple(body.tags),
                owner_id=body.owner_id,
                state=body.state,
                pending_until=body.pending_until,
                time_minutes=body.time_minutes,
            )
        )
        note_audit(request, target=f'#{ticket.number}')
        return await detail(member, ticket.id)

    @router.get('/tickets/by-number/{number}')
    async def by_number(number: int, member: CurrentMember) -> TicketResponse:
        ticket = await bus.query(FindTicketByNumber(tenant_id=member.tenant_id, actor=actor_of(member), number=number))
        found = await detail(member, ticket.id)
        return TicketResponse(**found.model_dump(include=set(TicketResponse.model_fields)))

    @router.get('/tickets/{ticket_id}')
    async def show(ticket_id: Id, member: CurrentMember) -> TicketDetailResponse:
        return await detail(member, ticket_id)

    @router.patch('/tickets/{ticket_id}', dependencies=[Unaudited])
    async def update(ticket_id: Id, body: TicketChangesRequest, member: CurrentMember) -> TicketDetailResponse:
        """Changes what was sent; each change needs its right (`edit`, `assign`, `move` + `create` in the target)."""
        sent = body.model_fields_set
        values: dict[str, Any] = {name: getattr(body, name) for name in sent}
        if 'tags' in values:
            values['tags'] = tuple(body.tags or ())
        changes = TicketChanges(**values)
        await bus.execute(
            UpdateTicket(tenant_id=member.tenant_id, actor=actor_of(member), ticket_id=ticket_id, changes=changes)
        )
        return await detail(member, ticket_id)

    @router.delete(
        '/tickets/{ticket_id}', status_code=204, response_class=Response, dependencies=[audited('ticket.deleted')]
    )
    async def destroy(
        ticket_id: Id, request: Request, member: Annotated[Member, member_with('tickets.delete')]
    ) -> None:
        """Deletes the ticket with everything in it, for good."""
        ticket = await bus.execute(
            DeleteTicket(tenant_id=member.tenant_id, actor=actor_of(member), ticket_id=ticket_id)
        )
        note_audit(request, target=f'#{ticket.number}')

    @router.post('/tickets/bulk', dependencies=[Unaudited])
    async def bulk(body: BulkRequest, member: CurrentMember) -> BulkResponse:
        """The same changes for many tickets; those the caller may not change are listed with the reason."""
        sent = body.model_fields_set - {'ticket_ids', 'add_tags'}
        values: dict[str, Any] = {name: getattr(body, name) for name in sent}
        changes = TicketChanges(**values, add_tags=tuple(body.add_tags))
        result = await bus.execute(
            BulkUpdate(tenant_id=member.tenant_id, actor=actor_of(member), ticket_ids=body.ticket_ids, changes=changes)
        )
        return BulkResponse.of(result)

    @router.get('/tickets/{ticket_id}/similar')
    async def similar(ticket_id: Id, member: CurrentMember) -> TicketPageResponse:
        """Up to five tickets with words of this one's subject (e.g. the same problem of another customer)."""
        found = await bus.query(SimilarTickets(tenant_id=member.tenant_id, actor=actor_of(member), ticket_id=ticket_id))
        cards_found = await cards(member.tenant_id, [each.ticket.customer_id for each in found.items])
        return TicketPageResponse.of(list(found.items), found.total, cards_found)

    @router.get('/assistant')
    async def assistant(member: CurrentMember) -> AssistantResponse:
        """Whether the AI assistant is set up on this server (`ZENDILOHUB_ANTHROPIC_API_KEY`)."""
        return AssistantResponse(enabled=await bus.query(AssistantStatus()))

    @router.post('/tickets/{ticket_id}/assist', dependencies=[Unaudited])
    async def assist(ticket_id: Id, body: AssistRequest, member: CurrentMember) -> AssistResponse:
        """A summary of the ticket or a draft reply by the AI assistant; nothing is saved or sent."""
        text = await bus.query(
            Assist(tenant_id=member.tenant_id, actor=actor_of(member), ticket_id=ticket_id, task=body.task)
        )
        return AssistResponse(text=text)

    @router.get('/tickets/{ticket_id}/messages')
    async def messages(ticket_id: Id, member: CurrentMember) -> list[MessageResponse]:
        listed = await bus.query(ListMessages(tenant_id=member.tenant_id, actor=actor_of(member), ticket_id=ticket_id))
        return [MessageResponse.of(each) for each in listed]

    @router.post('/tickets/{ticket_id}/messages', status_code=201, dependencies=[Unaudited])
    async def add_message(ticket_id: Id, body: MessageRequest, member: CurrentMember) -> MessageResponse:
        """A reply (`reply`), an internal note (`note`) or what the customer said; can change the state (`edit`)."""
        message = await bus.execute(
            AddMessage(
                tenant_id=member.tenant_id,
                actor=actor_of(member),
                ticket_id=ticket_id,
                kind=body.kind,
                body=body.body,
                direction=body.direction,
                state=body.state,
                pending_until=body.pending_until,
                time_minutes=body.time_minutes,
                mentions=body.mentions,
            )
        )
        return MessageResponse.of(message)

    @router.get('/tickets/{ticket_id}/history')
    async def history(ticket_id: Id, member: CurrentMember) -> list[HistoryEntryResponse]:
        listed = await bus.query(TicketHistory(tenant_id=member.tenant_id, actor=actor_of(member), ticket_id=ticket_id))
        return [HistoryEntryResponse.of(each) for each in listed]

    @router.put('/tickets/{ticket_id}/watch', status_code=204, response_class=Response, dependencies=[Unaudited])
    async def watch(ticket_id: Id, member: CurrentMember) -> None:
        await bus.execute(Watch(tenant_id=member.tenant_id, actor=actor_of(member), ticket_id=ticket_id))

    @router.delete('/tickets/{ticket_id}/watch', status_code=204, response_class=Response, dependencies=[Unaudited])
    async def unwatch(ticket_id: Id, member: CurrentMember) -> None:
        await bus.execute(Watch(tenant_id=member.tenant_id, actor=actor_of(member), ticket_id=ticket_id, on=False))

    @router.post('/tickets/{ticket_id}/links', status_code=201, dependencies=[Unaudited])
    async def link(ticket_id: Id, body: LinkRequest, member: CurrentMember) -> TicketDetailResponse:
        await bus.execute(
            LinkTickets(
                tenant_id=member.tenant_id,
                actor=actor_of(member),
                ticket_id=ticket_id,
                other_number=body.number,
                kind=body.kind,
            )
        )
        return await detail(member, ticket_id)

    @router.delete(
        '/tickets/{ticket_id}/links/{other_id}', status_code=204, response_class=Response, dependencies=[Unaudited]
    )
    async def unlink(ticket_id: Id, other_id: Id, member: CurrentMember) -> None:
        await bus.execute(
            UnlinkTickets(tenant_id=member.tenant_id, actor=actor_of(member), ticket_id=ticket_id, other_id=other_id)
        )

    @router.post('/tickets/{ticket_id}/merge', dependencies=[audited('ticket.merged')])
    async def merge(ticket_id: Id, body: MergeRequest, request: Request, member: CurrentMember) -> TicketDetailResponse:
        """Merges this ticket into the one with the number; answers with that one."""
        target = await bus.execute(
            MergeTicket(
                tenant_id=member.tenant_id, actor=actor_of(member), ticket_id=ticket_id, into_number=body.number
            )
        )
        note_audit(request, target=f'#{target.number}')
        return await detail(member, target.id)

    @router.post('/tickets/{ticket_id}/split', status_code=201, dependencies=[Unaudited])
    async def split(ticket_id: Id, body: SplitRequest, member: CurrentMember) -> TicketDetailResponse:
        """A new ticket from one message of this one."""
        ticket = await bus.execute(
            SplitTicket(
                tenant_id=member.tenant_id,
                actor=actor_of(member),
                ticket_id=ticket_id,
                message_id=body.message_id,
                subject=body.subject,
            )
        )
        return await detail(member, ticket.id)

    @router.get('/tickets/{ticket_id}/time')
    async def time(ticket_id: Id, member: CurrentMember) -> list[TimeEntryResponse]:
        listed = await bus.query(TicketTime(tenant_id=member.tenant_id, actor=actor_of(member), ticket_id=ticket_id))
        return [TimeEntryResponse.of(each) for each in listed]

    @router.post('/tickets/{ticket_id}/time', status_code=201, dependencies=[Unaudited])
    async def record_time(ticket_id: Id, body: TimeRequest, member: CurrentMember) -> TimeEntryResponse:
        entry = await bus.execute(
            RecordTime(tenant_id=member.tenant_id, actor=actor_of(member), ticket_id=ticket_id, minutes=body.minutes)
        )
        return TimeEntryResponse.of(entry)

    @router.get('/ticket-fields')
    async def fields(member: CurrentMember) -> list[FieldResponse]:
        """The organization's own ticket fields, in their order."""
        return [FieldResponse.of(each) for each in await bus.query(ListFields(member.tenant_id))]

    @router.post('/ticket-fields', status_code=201, dependencies=[audited('ticket_field.created')])
    async def create_field(body: FieldRequest, request: Request, member: FieldManager) -> FieldResponse:
        saved = await bus.execute(
            SaveField(
                tenant_id=member.tenant_id,
                key=body.key,
                label=body.label,
                kind=body.kind,
                options=tuple(body.options),
            )
        )
        note_audit(request, target=saved.key)
        return FieldResponse.of(saved)

    @router.patch('/ticket-fields/{field_id}', dependencies=[audited('ticket_field.updated')])
    async def update_field(field_id: Id, body: FieldRequest, request: Request, member: FieldManager) -> FieldResponse:
        """Label and choices; key and kind stay."""
        saved = await bus.execute(
            SaveField(
                tenant_id=member.tenant_id,
                key=body.key,
                label=body.label,
                kind=body.kind,
                options=tuple(body.options),
                field_id=field_id,
            )
        )
        note_audit(request, target=saved.key)
        return FieldResponse.of(saved)

    @router.delete(
        '/ticket-fields/{field_id}',
        status_code=204,
        response_class=Response,
        dependencies=[audited('ticket_field.deleted')],
    )
    async def delete_field(field_id: Id, request: Request, member: FieldManager) -> None:
        """With its values in every ticket."""
        deleted = await bus.execute(DeleteField(tenant_id=member.tenant_id, field_id=field_id))
        note_audit(request, target=deleted.key)

    @router.get('/tickets/{ticket_id}/checklist')
    async def checklist(ticket_id: Id, member: CurrentMember) -> list[ChecklistItemResponse]:
        listed = await bus.query(Checklist(tenant_id=member.tenant_id, actor=actor_of(member), ticket_id=ticket_id))
        return [ChecklistItemResponse.of(each) for each in listed]

    @router.post('/tickets/{ticket_id}/checklist', status_code=201, dependencies=[Unaudited])
    async def add_checklist_item(
        ticket_id: Id, body: ChecklistItemRequest, member: CurrentMember
    ) -> ChecklistItemResponse:
        item = await bus.execute(
            AddChecklistItem(tenant_id=member.tenant_id, actor=actor_of(member), ticket_id=ticket_id, text=body.text)
        )
        return ChecklistItemResponse.of(item)

    @router.patch('/tickets/{ticket_id}/checklist/{item_id}', dependencies=[Unaudited])
    async def change_checklist_item(
        ticket_id: Id, item_id: Id, body: ChecklistChangeRequest, member: CurrentMember
    ) -> ChecklistItemResponse:
        item = await bus.execute(
            ChangeChecklistItem(
                tenant_id=member.tenant_id,
                actor=actor_of(member),
                ticket_id=ticket_id,
                item_id=item_id,
                text=body.text,
                done=body.done,
            )
        )
        return ChecklistItemResponse.of(item)

    @router.delete(
        '/tickets/{ticket_id}/checklist/{item_id}', status_code=204, response_class=Response, dependencies=[Unaudited]
    )
    async def delete_checklist_item(ticket_id: Id, item_id: Id, member: CurrentMember) -> None:
        await bus.execute(
            ChangeChecklistItem(
                tenant_id=member.tenant_id, actor=actor_of(member), ticket_id=ticket_id, item_id=item_id, delete=True
            )
        )

    @router.put('/tickets/{ticket_id}/presence', dependencies=[Unaudited])
    async def presence(ticket_id: Id, body: PresenceRequest, member: CurrentPerson) -> list[ViewerResponse]:
        """The caller has the ticket open (and writes); answers who else has (call it every 15 seconds)."""
        others = await bus.execute(
            BeHere(tenant_id=member.tenant_id, actor=actor_of(member), ticket_id=ticket_id, writing=body.writing)
        )
        return [ViewerResponse(user_id=user_id, writing=writing) for user_id, writing in others]

    @router.get('/queues/{queue_id}/assignees')
    async def assignees(queue_id: Id, member: CurrentMember) -> list[str]:
        """The members tickets of the queue may go to (who may reply in it), by user id."""
        return await bus.query(Assignees(tenant_id=member.tenant_id, actor=actor_of(member), queue_id=queue_id))

    return router
