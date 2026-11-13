from dataclasses import dataclass

from zendilohub.core.bus.message import Command
from zendilohub.core.domain.clock import Clock
from zendilohub.core.domain.id_generator import IdGenerator
from zendilohub.core.domain.transaction import TransactionManager

from ...domain.exceptions import (
    CompanyNotFoundError,
    ContactEmailTakenError,
    ContactHasTicketsError,
    ContactNotFoundError,
    InvalidContactError,
)
from ...domain.models.contact import Contact
from ...domain.models.text import InvalidValueError, clean_email, clean_phone, domain_of
from ...domain.ports.repositories import CompanyRepository, ContactRepository
from ...domain.ports.ticket_usage import CustomerTickets


@dataclass(frozen=True, kw_only=True)
class ContactFields:
    name: str = ''
    email: str | None = None
    phone: str | None = None
    company_id: str | None = None
    notes: str = ''


@dataclass(frozen=True, kw_only=True)
class CreateContact(Command[Contact]):
    tenant_id: str
    fields: ContactFields


class _Checks:
    def __init__(self, contacts: ContactRepository, companies: CompanyRepository) -> None:
        self._contacts = contacts
        self._companies = companies

    async def check(self, contact: Contact) -> None:
        if contact.company_id is not None and await self._companies.find(contact.tenant_id, contact.company_id) is None:
            raise CompanyNotFoundError()
        if contact.email is not None:
            other = await self._contacts.find_by_email(contact.tenant_id, contact.email)
            if other is not None and other.id != contact.id:
                raise ContactEmailTakenError()


class CreateContactHandler:
    def __init__(
        self,
        contacts: ContactRepository,
        companies: CompanyRepository,
        transactions: TransactionManager,
        ids: IdGenerator,
        clock: Clock,
    ) -> None:
        self._contacts = contacts
        self._companies = companies
        self._checks = _Checks(contacts, companies)
        self._transactions = transactions
        self._ids = ids
        self._clock = clock

    async def handle(self, command: CreateContact) -> Contact:
        fields = command.fields
        contact = Contact.create(
            id=self._ids.new_id(),
            tenant_id=command.tenant_id,
            name=fields.name,
            email=fields.email,
            phone=fields.phone,
            company_id=fields.company_id,
            notes=fields.notes,
            now=self._clock.now(),
        )
        async with self._transactions.transaction():
            if contact.company_id is None and contact.email is not None:
                company = await self._companies.find_by_domain(command.tenant_id, domain_of(contact.email))
                contact.company_id = company.id if company else None
            await self._checks.check(contact)
            await self._contacts.save(contact)
        return contact


@dataclass(frozen=True, kw_only=True)
class UpdateContact(Command[Contact]):
    tenant_id: str
    contact_id: str
    fields: ContactFields


class UpdateContactHandler:
    def __init__(
        self,
        contacts: ContactRepository,
        companies: CompanyRepository,
        transactions: TransactionManager,
        clock: Clock,
    ) -> None:
        self._contacts = contacts
        self._checks = _Checks(contacts, companies)
        self._transactions = transactions
        self._clock = clock

    async def handle(self, command: UpdateContact) -> Contact:
        fields = command.fields
        async with self._transactions.transaction():
            contact = await self._contacts.find(command.tenant_id, command.contact_id)
            if contact is None:
                raise ContactNotFoundError()
            contact.change(
                name=fields.name,
                email=fields.email,
                phone=fields.phone,
                company_id=fields.company_id,
                notes=fields.notes,
                now=self._clock.now(),
            )
            await self._checks.check(contact)
            await self._contacts.save(contact)
        return contact


@dataclass(frozen=True, kw_only=True)
class DeleteContact(Command[Contact]):
    tenant_id: str
    contact_id: str


class DeleteContactHandler:
    def __init__(self, contacts: ContactRepository, tickets: CustomerTickets) -> None:
        self._contacts = contacts
        self._tickets = tickets

    async def handle(self, command: DeleteContact) -> Contact:
        contact = await self._contacts.find(command.tenant_id, command.contact_id)
        if contact is None:
            raise ContactNotFoundError()
        count = await self._tickets.of_customer(command.tenant_id, contact.id)
        if count:
            raise ContactHasTicketsError(count)
        await self._contacts.delete(command.tenant_id, contact.id)
        return contact


@dataclass(frozen=True, kw_only=True)
class IdentifyContact(Command[Contact]):
    """The contact with this e-mail address or phone number; made on first contact (a mail, a call, a form)."""

    tenant_id: str
    email: str | None
    name: str = ''
    phone: str | None = None


class IdentifyContactHandler:
    def __init__(
        self,
        contacts: ContactRepository,
        companies: CompanyRepository,
        transactions: TransactionManager,
        ids: IdGenerator,
        clock: Clock,
    ) -> None:
        self._contacts = contacts
        self._create = CreateContactHandler(contacts, companies, transactions, ids, clock)

    async def handle(self, command: IdentifyContact) -> Contact:
        try:
            email, phone = clean_email(command.email), clean_phone(command.phone)
        except InvalidValueError as invalid:
            raise InvalidContactError(str(invalid)) from None
        if email is not None and (found := await self._contacts.find_by_email(command.tenant_id, email)):
            return found
        if phone is not None and (found := await self._contacts.find_by_phone(command.tenant_id, phone)):
            return found
        fields = ContactFields(name=command.name, email=email, phone=phone)
        return await self._create.handle(CreateContact(tenant_id=command.tenant_id, fields=fields))
