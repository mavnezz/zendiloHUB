from pathlib import Path

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.database.migration import sql_migrations
from zendilohub.core.events.integration_events import TenantDeleted
from zendilohub.core.module import AppModule, ModuleContext

from .application.commands.companies import (
    CreateCompany,
    CreateCompanyHandler,
    DeleteCompany,
    DeleteCompanyHandler,
    ForgetTenant,
    ForgetTenantHandler,
    UpdateCompany,
    UpdateCompanyHandler,
)
from .application.commands.contacts import (
    CreateContact,
    CreateContactHandler,
    DeleteContact,
    DeleteContactHandler,
    IdentifyContact,
    IdentifyContactHandler,
    UpdateContact,
    UpdateContactHandler,
)
from .application.queries.customers import (
    ContactCards,
    ContactCardsHandler,
    GetCompany,
    GetCompanyHandler,
    GetContact,
    GetContactHandler,
    SearchCompanies,
    SearchCompaniesHandler,
    SearchContacts,
    SearchContactsHandler,
)
from .infrastructure.contract_adapters import BusContacts, ContractTickets
from .infrastructure.postgres_customers import PostgresCompanyRepository, PostgresContactRepository
from .ui.api.routes import customer_routes

MIGRATIONS = Path(__file__).parent / 'infrastructure' / 'migrations'


def create_customers_module(context: ModuleContext) -> AppModule:
    """
    The organization's customers: contacts (recognized by e-mail address or phone number) and their companies.
    Other modules find and show them through the `Contacts` contract.
    """
    db, clock, ids = context.db, context.clock, context.ids
    contacts = PostgresContactRepository(db)
    companies = PostgresCompanyRepository(db)
    bus = (
        CommandBus()
        .register(CreateContact, CreateContactHandler(contacts, companies, db, ids, clock))
        .register(UpdateContact, UpdateContactHandler(contacts, companies, db, clock))
        .register(DeleteContact, DeleteContactHandler(contacts, ContractTickets(context.contracts)))
        .register(IdentifyContact, IdentifyContactHandler(contacts, companies, db, ids, clock))
        .register(CreateCompany, CreateCompanyHandler(companies, ids, clock))
        .register(UpdateCompany, UpdateCompanyHandler(companies, clock))
        .register(DeleteCompany, DeleteCompanyHandler(companies, contacts, db))
        .register(ForgetTenant, ForgetTenantHandler(contacts))
        .register(SearchContacts, SearchContactsHandler(contacts, companies))
        .register(GetContact, GetContactHandler(contacts, companies))
        .register(ContactCards, ContactCardsHandler(contacts, companies))
        .register(SearchCompanies, SearchCompaniesHandler(companies))
        .register(GetCompany, GetCompanyHandler(companies))
    )

    async def tenant_deleted(event: TenantDeleted) -> None:
        await bus.execute(ForgetTenant(event.tenant_id))

    context.events.subscribe(TenantDeleted, tenant_deleted)
    context.contracts.contacts.provide(BusContacts(bus))

    return AppModule(name='customers', migrations=sql_migrations(MIGRATIONS), routers=[customer_routes(bus)])
