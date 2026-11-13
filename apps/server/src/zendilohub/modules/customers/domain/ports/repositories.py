from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from ..models.company import Company
from ..models.contact import Contact


@dataclass(frozen=True)
class ContactPage:
    items: Sequence[Contact]
    total: int


@dataclass(frozen=True)
class CompanyPage:
    items: Sequence[Company]
    total: int
    contact_counts: dict[str, int]


class ContactRepository(Protocol):
    async def find(self, tenant_id: str, contact_id: str) -> Contact | None: ...

    async def find_many(self, tenant_id: str, contact_ids: Sequence[str]) -> Sequence[Contact]: ...

    async def find_by_email(self, tenant_id: str, email: str) -> Contact | None: ...

    async def find_by_phone(self, tenant_id: str, phone: str) -> Contact | None: ...

    async def search(
        self, tenant_id: str, query: str, *, company_id: str | None, offset: int, limit: int
    ) -> ContactPage:
        """Name, e-mail address or phone number containing `query`, by name."""
        ...

    async def save(self, contact: Contact) -> None: ...

    async def delete(self, tenant_id: str, contact_id: str) -> None: ...

    async def leave_company(self, tenant_id: str, company_id: str) -> None:
        """The company is deleted: its contacts stay, without it."""
        ...

    async def delete_tenant(self, tenant_id: str) -> None:
        """Contacts and companies of the organization."""
        ...


class CompanyRepository(Protocol):
    async def find(self, tenant_id: str, company_id: str) -> Company | None: ...

    async def find_by_domain(self, tenant_id: str, domain: str) -> Company | None: ...

    async def find_many(self, tenant_id: str, company_ids: Sequence[str]) -> Sequence[Company]: ...

    async def search(self, tenant_id: str, query: str, *, offset: int, limit: int) -> CompanyPage: ...

    async def name_taken(self, tenant_id: str, name: str, *, except_id: str | None = None) -> bool: ...

    async def domain_taken(self, tenant_id: str, domain: str, *, except_id: str | None = None) -> bool: ...

    async def save(self, company: Company) -> None: ...

    async def delete(self, tenant_id: str, company_id: str) -> None: ...
