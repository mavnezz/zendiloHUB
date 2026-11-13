from dataclasses import dataclass

from zendilohub.core.bus.message import Command
from zendilohub.core.domain.clock import Clock
from zendilohub.core.domain.id_generator import IdGenerator
from zendilohub.core.domain.transaction import TransactionManager

from ...domain.exceptions import CompanyDomainTakenError, CompanyNameTakenError, CompanyNotFoundError
from ...domain.models.company import Company
from ...domain.ports.repositories import CompanyRepository, ContactRepository


@dataclass(frozen=True, kw_only=True)
class CompanyFields:
    name: str
    domain: str | None = None
    notes: str = ''


async def _check(companies: CompanyRepository, company: Company, except_id: str | None = None) -> None:
    if await companies.name_taken(company.tenant_id, company.name, except_id=except_id):
        raise CompanyNameTakenError()
    if company.domain and await companies.domain_taken(company.tenant_id, company.domain, except_id=except_id):
        raise CompanyDomainTakenError()


@dataclass(frozen=True, kw_only=True)
class CreateCompany(Command[Company]):
    tenant_id: str
    fields: CompanyFields


class CreateCompanyHandler:
    def __init__(self, companies: CompanyRepository, ids: IdGenerator, clock: Clock) -> None:
        self._companies = companies
        self._ids = ids
        self._clock = clock

    async def handle(self, command: CreateCompany) -> Company:
        fields = command.fields
        company = Company.create(
            id=self._ids.new_id(),
            tenant_id=command.tenant_id,
            name=fields.name,
            domain=fields.domain,
            notes=fields.notes,
            now=self._clock.now(),
        )
        await _check(self._companies, company)
        await self._companies.save(company)
        return company


@dataclass(frozen=True, kw_only=True)
class UpdateCompany(Command[Company]):
    tenant_id: str
    company_id: str
    fields: CompanyFields


class UpdateCompanyHandler:
    def __init__(self, companies: CompanyRepository, clock: Clock) -> None:
        self._companies = companies
        self._clock = clock

    async def handle(self, command: UpdateCompany) -> Company:
        company = await self._companies.find(command.tenant_id, command.company_id)
        if company is None:
            raise CompanyNotFoundError()
        fields = command.fields
        company.change(name=fields.name, domain=fields.domain, notes=fields.notes, now=self._clock.now())
        await _check(self._companies, company, company.id)
        await self._companies.save(company)
        return company


@dataclass(frozen=True, kw_only=True)
class DeleteCompany(Command[Company]):
    """Its contacts stay, without a company."""

    tenant_id: str
    company_id: str


class DeleteCompanyHandler:
    def __init__(
        self, companies: CompanyRepository, contacts: ContactRepository, transactions: TransactionManager
    ) -> None:
        self._companies = companies
        self._contacts = contacts
        self._transactions = transactions

    async def handle(self, command: DeleteCompany) -> Company:
        async with self._transactions.transaction():
            company = await self._companies.find(command.tenant_id, command.company_id)
            if company is None:
                raise CompanyNotFoundError()
            await self._contacts.leave_company(command.tenant_id, company.id)
            await self._companies.delete(command.tenant_id, company.id)
        return company


@dataclass(frozen=True)
class ForgetTenant(Command[None]):
    tenant_id: str


class ForgetTenantHandler:
    def __init__(self, contacts: ContactRepository) -> None:
        self._contacts = contacts

    async def handle(self, command: ForgetTenant) -> None:
        await self._contacts.delete_tenant(command.tenant_id)
