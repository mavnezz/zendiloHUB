from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class ContactCard:
    """What other modules show of a customer: a contact with their company."""

    id: str
    name: str
    email: str | None
    phone: str | None
    company_id: str | None
    company_name: str | None
