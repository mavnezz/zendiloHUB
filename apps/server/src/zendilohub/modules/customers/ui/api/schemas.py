from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from ...application.queries.customers import ContactList, ContactWithCompany
from ...domain.models.company import Company
from ...domain.models.text import NAME_MAX, NOTES_MAX, PHONE_MAX
from ...domain.ports.repositories import CompanyPage


class Request(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ContactRequest(Request):
    """At least a name, an e-mail address or a phone number."""

    name: str = Field(default='', max_length=NAME_MAX)
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=PHONE_MAX)
    company_id: str | None = Field(default=None, max_length=36)
    notes: str = Field(default='', max_length=NOTES_MAX)


class CompanyRequest(Request):
    name: str = Field(max_length=NAME_MAX)
    domain: str | None = Field(default=None, max_length=253)
    """New contacts with an address of this domain join the company on their own."""
    notes: str = Field(default='', max_length=NOTES_MAX)


class CompanyRef(BaseModel):
    id: str
    name: str


class ContactResponse(BaseModel):
    id: str
    name: str
    email: str | None
    phone: str | None
    company: CompanyRef | None
    notes: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, found: ContactWithCompany) -> ContactResponse:
        contact, company = found.contact, found.company
        return cls(
            id=contact.id,
            name=contact.name,
            email=contact.email,
            phone=contact.phone,
            company=CompanyRef(id=company.id, name=company.name) if company else None,
            notes=contact.notes,
            created_at=contact.created_at,
            updated_at=contact.updated_at,
        )


class ContactPageResponse(BaseModel):
    items: list[ContactResponse]
    total: int

    @classmethod
    def of(cls, page: ContactList) -> ContactPageResponse:
        return cls(items=[ContactResponse.of(each) for each in page.items], total=page.total)


class CompanyResponse(BaseModel):
    id: str
    name: str
    domain: str | None
    notes: str
    contact_count: int
    created_at: datetime

    @classmethod
    def of(cls, company: Company, contacts: int = 0) -> CompanyResponse:
        return cls(
            id=company.id,
            name=company.name,
            domain=company.domain,
            notes=company.notes,
            contact_count=contacts,
            created_at=company.created_at,
        )


class CompanyPageResponse(BaseModel):
    items: list[CompanyResponse]
    total: int

    @classmethod
    def of(cls, page: CompanyPage) -> CompanyPageResponse:
        return cls(
            items=[CompanyResponse.of(each, page.contact_counts.get(each.id, 0)) for each in page.items],
            total=page.total,
        )
