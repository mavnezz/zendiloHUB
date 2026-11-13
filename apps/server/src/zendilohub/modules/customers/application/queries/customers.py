from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from zendilohub.core.bus.message import Query

from ...domain.exceptions import CompanyNotFoundError, ContactNotFoundError
from ...domain.models.company import Company
from ...domain.models.contact import Contact
from ...domain.ports.repositories import CompanyPage, CompanyRepository, ContactRepository


@dataclass(frozen=True)
class ContactWithCompany:
    contact: Contact
    company: Company | None


@dataclass(frozen=True)
class ContactList:
    items: Sequence[ContactWithCompany]
    total: int


async def _with_companies(
    companies: CompanyRepository, tenant_id: str, contacts: Sequence[Contact]
) -> list[ContactWithCompany]:
    ids = sorted({contact.company_id for contact in contacts if contact.company_id})
    by_id = {company.id: company for company in await companies.find_many(tenant_id, ids)} if ids else {}
    return [
        ContactWithCompany(contact, by_id.get(contact.company_id) if contact.company_id else None)
        for contact in contacts
    ]


@dataclass(frozen=True, kw_only=True)
class SearchContacts(Query[ContactList]):
    tenant_id: str
    query: str = ''
    company_id: str | None = None
    offset: int = 0
    limit: int = 50


class SearchContactsHandler:
    def __init__(self, contacts: ContactRepository, companies: CompanyRepository) -> None:
        self._contacts = contacts
        self._companies = companies

    async def handle(self, query: SearchContacts) -> ContactList:
        page = await self._contacts.search(
            query.tenant_id, query.query.strip(), company_id=query.company_id, offset=query.offset, limit=query.limit
        )
        return ContactList(await _with_companies(self._companies, query.tenant_id, page.items), page.total)


@dataclass(frozen=True, kw_only=True)
class GetContact(Query[ContactWithCompany]):
    tenant_id: str
    contact_id: str


class GetContactHandler:
    def __init__(self, contacts: ContactRepository, companies: CompanyRepository) -> None:
        self._contacts = contacts
        self._companies = companies

    async def handle(self, query: GetContact) -> ContactWithCompany:
        contact = await self._contacts.find(query.tenant_id, query.contact_id)
        if contact is None:
            raise ContactNotFoundError()
        return (await _with_companies(self._companies, query.tenant_id, [contact]))[0]


@dataclass(frozen=True, kw_only=True)
class ContactCards(Query[Mapping[str, ContactWithCompany]]):
    tenant_id: str
    contact_ids: Sequence[str]


class ContactCardsHandler:
    def __init__(self, contacts: ContactRepository, companies: CompanyRepository) -> None:
        self._contacts = contacts
        self._companies = companies

    async def handle(self, query: ContactCards) -> Mapping[str, ContactWithCompany]:
        if not query.contact_ids:
            return {}
        found = await self._contacts.find_many(query.tenant_id, query.contact_ids)
        return {each.contact.id: each for each in await _with_companies(self._companies, query.tenant_id, found)}


@dataclass(frozen=True, kw_only=True)
class SearchCompanies(Query[CompanyPage]):
    tenant_id: str
    query: str = ''
    offset: int = 0
    limit: int = 50


class SearchCompaniesHandler:
    def __init__(self, companies: CompanyRepository) -> None:
        self._companies = companies

    async def handle(self, query: SearchCompanies) -> CompanyPage:
        return await self._companies.search(
            query.tenant_id, query.query.strip(), offset=query.offset, limit=query.limit
        )


@dataclass(frozen=True, kw_only=True)
class GetCompany(Query[Company]):
    tenant_id: str
    company_id: str


class GetCompanyHandler:
    def __init__(self, companies: CompanyRepository) -> None:
        self._companies = companies

    async def handle(self, query: GetCompany) -> Company:
        company = await self._companies.find(query.tenant_id, query.company_id)
        if company is None:
            raise CompanyNotFoundError()
        return company
