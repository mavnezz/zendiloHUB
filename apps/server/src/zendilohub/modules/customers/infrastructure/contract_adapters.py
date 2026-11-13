from collections.abc import Mapping

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.contracts import ContactCard, Contracts

from ..application.commands.contacts import IdentifyContact
from ..application.queries.customers import ContactCards, ContactWithCompany, SearchContacts


def card_of(found: ContactWithCompany) -> ContactCard:
    contact, company = found.contact, found.company
    return ContactCard(
        id=contact.id,
        name=contact.name,
        email=contact.email,
        phone=contact.phone,
        company_id=company.id if company else None,
        company_name=company.name if company else None,
    )


class BusContacts:
    """Customers' side of the `Contacts` contract."""

    def __init__(self, bus: CommandBus) -> None:
        self._bus = bus

    async def identify(
        self, tenant_id: str, *, email: str | None, name: str = '', phone: str | None = None
    ) -> ContactCard:
        contact = await self._bus.execute(IdentifyContact(tenant_id=tenant_id, email=email, name=name, phone=phone))
        return (await self.cards(tenant_id, [contact.id]))[contact.id]

    async def cards(self, tenant_id: str, contact_ids: list[str]) -> Mapping[str, ContactCard]:
        found = await self._bus.query(ContactCards(tenant_id=tenant_id, contact_ids=contact_ids))
        return {contact_id: card_of(each) for contact_id, each in found.items()}

    async def of_company(self, tenant_id: str, company_id: str) -> list[str]:
        listed = await self._bus.query(SearchContacts(tenant_id=tenant_id, company_id=company_id, limit=10_000))
        return [each.contact.id for each in listed.items]


class ContractTickets:
    """`CustomerTickets` through the tickets module's `TicketUsage` contract."""

    def __init__(self, contracts: Contracts) -> None:
        self._contracts = contracts

    async def of_customer(self, tenant_id: str, contact_id: str) -> int:
        return await self._contracts.ticket_usage.get().of_customer(tenant_id, contact_id)
