from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, Request, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.config import AppConfig
from zendilohub.core.domain.files import FileData, FileInfo
from zendilohub.core.domain.portal import PortalMessage, PortalThread, PortalTicket
from zendilohub.core.http.access import Member, Public, member_with
from zendilohub.core.http.audit import Unaudited, audited
from zendilohub.core.http.files import file_response, read_upload
from zendilohub.core.http.ids import Id

from ...application.commands.portal import (
    Answer,
    GetSettings,
    MyFile,
    MyThread,
    MyTickets,
    OpenTicket,
    RequestLink,
    SaveSettings,
    SignOut,
    Verify,
    Visitor,
    WhoIs,
)
from ...domain.models.portal import SESSION_LIFETIME, PortalSettings

COOKIE = 'zendilohub_portal'
Admin = Annotated[Member, member_with('tenant.manage', people_only=True)]


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class PortalSettingsBody(Strict):
    enabled: bool = False
    queue_id: Id | None = None
    """Where new tickets of the portal go."""
    company_tickets: bool = False
    """Contacts also see the tickets of their company's other contacts."""


class PortalLinkRequest(Strict):
    email: str = Field(max_length=254)


class PortalTokenRequest(Strict):
    token: str = Field(max_length=200)


class PortalTicketResponse(BaseModel):
    id: str
    number: int
    subject: str
    state: Literal['open', 'waiting', 'closed']
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, ticket: PortalTicket) -> PortalTicketResponse:
        return cls(
            id=ticket.id,
            number=ticket.number,
            subject=ticket.subject,
            state=ticket.state,  # type: ignore[arg-type]
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
        )


class PortalFileResponse(BaseModel):
    id: str
    filename: str
    content_type: str
    size: int

    @classmethod
    def of(cls, file: FileInfo) -> PortalFileResponse:
        return cls(id=file.id, filename=file.filename, content_type=file.content_type, size=file.size)


class PortalMessageResponse(BaseModel):
    id: str
    from_customer: bool
    author_name: str
    body: str
    attachments: list[PortalFileResponse]
    created_at: datetime

    @classmethod
    def of(cls, message: PortalMessage) -> PortalMessageResponse:
        return cls(
            id=message.id,
            from_customer=message.from_customer,
            author_name=message.author_name,
            body=message.body,
            attachments=[PortalFileResponse.of(each) for each in message.attachments],
            created_at=message.created_at,
        )


class PortalThreadResponse(BaseModel):
    ticket: PortalTicketResponse
    messages: list[PortalMessageResponse]

    @classmethod
    def of(cls, thread: PortalThread) -> PortalThreadResponse:
        return cls(
            ticket=PortalTicketResponse.of(thread.ticket),
            messages=[PortalMessageResponse.of(each) for each in thread.messages],
        )


class VisitorResponse(BaseModel):
    name: str
    email: str | None
    company_name: str | None
    company_tickets: bool

    @classmethod
    def of(cls, visitor: Visitor) -> VisitorResponse:
        return cls(
            name=visitor.contact.name,
            email=visitor.contact.email,
            company_name=visitor.contact.company_name,
            company_tickets=visitor.settings.company_tickets and bool(visitor.contact.company_id),
        )


def portal_settings_routes(bus: CommandBus) -> APIRouter:
    router = APIRouter(prefix='/tenants/{tenant_id}', tags=['portal'])

    @router.get('/portal-settings')
    async def settings(member: Admin) -> PortalSettingsBody:
        found = await bus.query(GetSettings(member.tenant_id))
        return PortalSettingsBody(enabled=found.enabled, queue_id=found.queue_id, company_tickets=found.company_tickets)

    @router.put('/portal-settings', dependencies=[audited('portal.changed')])
    async def save(body: PortalSettingsBody, member: Admin) -> PortalSettingsBody:
        saved = await bus.execute(SaveSettings(PortalSettings(tenant_id=member.tenant_id, **body.model_dump())))
        return PortalSettingsBody(enabled=saved.enabled, queue_id=saved.queue_id, company_tickets=saved.company_tickets)

    return router


def portal_routes(bus: CommandBus, config: AppConfig) -> APIRouter:
    """The customer portal: customers sign in with a link sent to their address and see and answer their tickets."""
    router = APIRouter(prefix='/portal/{tenant_id}', tags=['portal'])

    async def visitor(request: Request, tenant_id: str) -> Visitor:
        return await bus.query(WhoIs(tenant_id, request.cookies.get(COOKIE, '')))

    async def read(files: list[UploadFile] | None) -> tuple[FileData, ...]:
        return tuple([await read_upload(each, config.max_upload_bytes) for each in files or []])

    @router.post('/login', status_code=202, response_class=Response, dependencies=[Public, Unaudited])
    async def login(tenant_id: Id, body: PortalLinkRequest, request: Request) -> None:
        """Sends a sign-in link if the address belongs to a contact (the answer is the same either way)."""
        await bus.execute(
            RequestLink(
                tenant_id=tenant_id,
                email=body.email,
                link_base=config.public_url or str(request.base_url).rstrip('/'),
            )
        )

    @router.post('/verify', dependencies=[Public, Unaudited])
    async def verify(tenant_id: Id, body: PortalTokenRequest, response: Response) -> VisitorResponse:
        signed_in = await bus.execute(Verify(body.token))
        response.set_cookie(
            COOKIE,
            signed_in.token,
            max_age=int(SESSION_LIFETIME.total_seconds()),
            httponly=True,
            samesite='lax',
            secure=(config.public_url or '').startswith('https://'),
            path='/api/v1/portal',
        )
        return VisitorResponse.of(await bus.query(WhoIs(tenant_id, signed_in.token)))

    @router.post('/logout', status_code=204, response_class=Response, dependencies=[Public, Unaudited])
    async def logout(tenant_id: Id, request: Request, response: Response) -> None:
        await bus.execute(SignOut(request.cookies.get(COOKIE, '')))
        response.delete_cookie(COOKIE, path='/api/v1/portal')

    @router.get('/me', dependencies=[Public, Unaudited])
    async def me(tenant_id: Id, request: Request) -> VisitorResponse:
        return VisitorResponse.of(await visitor(request, tenant_id))

    @router.get('/tickets', dependencies=[Public, Unaudited])
    async def tickets(tenant_id: Id, request: Request) -> list[PortalTicketResponse]:
        found = await bus.query(MyTickets(await visitor(request, tenant_id)))
        return [PortalTicketResponse.of(each) for each in found]

    @router.post('/tickets', status_code=201, dependencies=[Public, Unaudited])
    async def create(
        tenant_id: Id,
        request: Request,
        subject: Annotated[str, Form(max_length=250)],
        body: Annotated[str, Form(max_length=50_000)],
        files: Annotated[list[UploadFile] | None, File()] = None,
    ) -> PortalTicketResponse:
        """A new request (multipart: `subject`, `body` and up to five `files`)."""
        who = await visitor(request, tenant_id)
        ticket = await bus.execute(OpenTicket(who, subject, body, await read(files)))
        return PortalTicketResponse.of(ticket)

    @router.get('/tickets/{ticket_id}', dependencies=[Public, Unaudited])
    async def thread(tenant_id: Id, ticket_id: Id, request: Request) -> PortalThreadResponse:
        return PortalThreadResponse.of(await bus.query(MyThread(await visitor(request, tenant_id), ticket_id)))

    @router.post('/tickets/{ticket_id}/messages', dependencies=[Public, Unaudited])
    async def answer(
        tenant_id: Id,
        ticket_id: Id,
        request: Request,
        body: Annotated[str, Form(max_length=50_000)] = '',
        files: Annotated[list[UploadFile] | None, File()] = None,
    ) -> PortalThreadResponse:
        """A reply (multipart: `body` and up to five `files`)."""
        who = await visitor(request, tenant_id)
        return PortalThreadResponse.of(await bus.execute(Answer(who, ticket_id, body, await read(files))))

    @router.get(
        '/tickets/{ticket_id}/attachments/{attachment_id}',
        response_class=Response,
        dependencies=[Public, Unaudited],
    )
    async def download(tenant_id: Id, ticket_id: Id, attachment_id: Id, request: Request) -> Response:
        found = await bus.query(MyFile(await visitor(request, tenant_id), ticket_id, attachment_id))
        return file_response(found.content, filename=found.filename, content_type=found.content_type)

    return router
