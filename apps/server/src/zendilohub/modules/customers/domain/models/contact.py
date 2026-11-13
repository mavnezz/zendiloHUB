from dataclasses import dataclass
from datetime import datetime

from ..exceptions import InvalidContactError
from .text import NAME_MAX, NOTES_MAX, InvalidValueError, clean_email, clean_name, clean_phone


@dataclass(kw_only=True)
class Contact:
    """
    A customer: someone who writes to the organization. Contacts have no login; they are recognized by their e-mail
    address (unique in the organization) or phone number. A contact may belong to a company.
    """

    id: str
    tenant_id: str
    name: str
    email: str | None
    phone: str | None
    company_id: str | None
    notes: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        id: str,
        tenant_id: str,
        name: str,
        email: str | None,
        phone: str | None,
        company_id: str | None,
        notes: str,
        now: datetime,
    ) -> Contact:
        contact = cls(
            id=id,
            tenant_id=tenant_id,
            name='',
            email=None,
            phone=None,
            company_id=None,
            notes='',
            created_at=now,
            updated_at=now,
        )
        contact.change(name=name, email=email, phone=phone, company_id=company_id, notes=notes, now=now)
        return contact

    def change(
        self,
        *,
        name: str,
        email: str | None,
        phone: str | None,
        company_id: str | None,
        notes: str,
        now: datetime,
    ) -> None:
        name, notes = clean_name(name), notes.strip()
        try:
            cleaned_email, cleaned_phone = clean_email(email), clean_phone(phone)
        except InvalidValueError as invalid:
            raise InvalidContactError(str(invalid)) from None
        if len(name) > NAME_MAX:
            raise InvalidContactError('name')
        if len(notes) > NOTES_MAX:
            raise InvalidContactError('notes')
        if not (name or cleaned_email or cleaned_phone):
            raise InvalidContactError('name')
        self.name = name or (cleaned_email or cleaned_phone or '')
        self.email, self.phone, self.company_id, self.notes = cleaned_email, cleaned_phone, company_id, notes
        self.updated_at = now
