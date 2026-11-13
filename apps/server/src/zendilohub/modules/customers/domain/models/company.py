from dataclasses import dataclass
from datetime import datetime

from ..exceptions import InvalidCompanyError
from .text import NAME_MAX, NOTES_MAX, InvalidValueError, clean_domain, clean_name


@dataclass(kw_only=True)
class Company:
    """
    A customer organization. New contacts whose e-mail address ends in the company's domain join it on their own
    (like Zammad's organization domains).
    """

    id: str
    tenant_id: str
    name: str
    domain: str | None
    notes: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(cls, *, id: str, tenant_id: str, name: str, domain: str | None, notes: str, now: datetime) -> Company:
        company = cls(id=id, tenant_id=tenant_id, name='', domain=None, notes='', created_at=now, updated_at=now)
        company.change(name=name, domain=domain, notes=notes, now=now)
        return company

    def change(self, *, name: str, domain: str | None, notes: str, now: datetime) -> None:
        name, notes = clean_name(name), notes.strip()
        try:
            cleaned = clean_domain(domain)
        except InvalidValueError:
            raise InvalidCompanyError('domain') from None
        if not 1 <= len(name) <= NAME_MAX:
            raise InvalidCompanyError('name')
        if len(notes) > NOTES_MAX:
            raise InvalidCompanyError('notes')
        self.name, self.domain, self.notes, self.updated_at = name, cleaned, notes, now
