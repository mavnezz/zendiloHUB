from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.http.access import Member, member_with
from zendilohub.core.http.audit import audited, note_audit
from zendilohub.core.http.ids import Id

from ...application.commands.companies import CompanyFields, CreateCompany, DeleteCompany, UpdateCompany
from ...application.commands.contacts import ContactFields, CreateContact, DeleteContact, UpdateContact
from ...application.queries.customers import (
    GetCompany,
    GetContact,
    SearchCompanies,
    SearchContacts,
)
from .schemas import (
    CompanyPageResponse,
    CompanyRequest,
    CompanyResponse,
    ContactPageResponse,
    ContactRequest,
    ContactResponse,
)

Viewer = Annotated[Member, member_with('customers.view')]
Editor = Annotated[Member, member_with('customers.manage')]


def _contact_fields(body: ContactRequest) -> ContactFields:
    return ContactFields(
        name=body.name, email=body.email, phone=body.phone, company_id=body.company_id, notes=body.notes
    )


def customer_routes(bus: CommandBus) -> APIRouter:
    router = APIRouter(prefix='/tenants/{tenant_id}', tags=['customers'])

    @router.get('/contacts')
    async def contacts(
        member: Viewer,
        q: Annotated[str, Query(max_length=200)] = '',
        company_id: Annotated[Id | None, Query()] = None,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> ContactPageResponse:
        """Contacts by name; `q` searches name, e-mail address and phone number."""
        page = await bus.query(
            SearchContacts(tenant_id=member.tenant_id, query=q, company_id=company_id, offset=offset, limit=limit)
        )
        return ContactPageResponse.of(page)

    @router.post('/contacts', status_code=201, dependencies=[audited('contact.created')])
    async def create_contact(body: ContactRequest, request: Request, member: Editor) -> ContactResponse:
        """A new contact; with an address of a company's domain they join that company."""
        contact = await bus.execute(CreateContact(tenant_id=member.tenant_id, fields=_contact_fields(body)))
        note_audit(request, target=contact.name)
        return ContactResponse.of(await bus.query(GetContact(tenant_id=member.tenant_id, contact_id=contact.id)))

    @router.get('/contacts/{contact_id}')
    async def contact(contact_id: Id, member: Viewer) -> ContactResponse:
        return ContactResponse.of(await bus.query(GetContact(tenant_id=member.tenant_id, contact_id=contact_id)))

    @router.patch('/contacts/{contact_id}', dependencies=[audited('contact.updated')])
    async def update_contact(contact_id: Id, body: ContactRequest, request: Request, member: Editor) -> ContactResponse:
        contact = await bus.execute(
            UpdateContact(tenant_id=member.tenant_id, contact_id=contact_id, fields=_contact_fields(body))
        )
        note_audit(request, target=contact.name)
        return ContactResponse.of(await bus.query(GetContact(tenant_id=member.tenant_id, contact_id=contact.id)))

    @router.delete(
        '/contacts/{contact_id}', status_code=204, response_class=Response, dependencies=[audited('contact.deleted')]
    )
    async def delete_contact(contact_id: Id, request: Request, member: Editor) -> None:
        """Only contacts without tickets."""
        contact = await bus.execute(DeleteContact(tenant_id=member.tenant_id, contact_id=contact_id))
        note_audit(request, target=contact.name)

    @router.get('/companies')
    async def companies(
        member: Viewer,
        q: Annotated[str, Query(max_length=200)] = '',
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> CompanyPageResponse:
        page = await bus.query(SearchCompanies(tenant_id=member.tenant_id, query=q, offset=offset, limit=limit))
        return CompanyPageResponse.of(page)

    @router.post('/companies', status_code=201, dependencies=[audited('company.created')])
    async def create_company(body: CompanyRequest, request: Request, member: Editor) -> CompanyResponse:
        company = await bus.execute(
            CreateCompany(
                tenant_id=member.tenant_id, fields=CompanyFields(name=body.name, domain=body.domain, notes=body.notes)
            )
        )
        note_audit(request, target=company.name)
        return CompanyResponse.of(company)

    @router.get('/companies/{company_id}')
    async def company(company_id: Id, member: Viewer) -> CompanyResponse:
        found = await bus.query(GetCompany(tenant_id=member.tenant_id, company_id=company_id))
        contacts = await bus.query(SearchContacts(tenant_id=member.tenant_id, company_id=found.id, limit=1))
        return CompanyResponse.of(found, contacts.total)

    @router.patch('/companies/{company_id}', dependencies=[audited('company.updated')])
    async def update_company(company_id: Id, body: CompanyRequest, request: Request, member: Editor) -> CompanyResponse:
        company = await bus.execute(
            UpdateCompany(
                tenant_id=member.tenant_id,
                company_id=company_id,
                fields=CompanyFields(name=body.name, domain=body.domain, notes=body.notes),
            )
        )
        note_audit(request, target=company.name)
        contacts = await bus.query(SearchContacts(tenant_id=member.tenant_id, company_id=company.id, limit=1))
        return CompanyResponse.of(company, contacts.total)

    @router.delete(
        '/companies/{company_id}', status_code=204, response_class=Response, dependencies=[audited('company.deleted')]
    )
    async def delete_company(company_id: Id, request: Request, member: Editor) -> None:
        """Its contacts stay, without a company."""
        company = await bus.execute(DeleteCompany(tenant_id=member.tenant_id, company_id=company_id))
        note_audit(request, target=company.name)

    return router
