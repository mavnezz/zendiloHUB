import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, get_args

from ..exceptions import InvalidFieldError
from .ticket import FieldValue

type FieldKind = Literal['text', 'number', 'select', 'checkbox', 'date']
FIELD_KINDS: tuple[FieldKind, ...] = get_args(FieldKind.__value__)
FIELDS_MAX = 50
OPTIONS_MAX = 100
_KEY = re.compile(r'^[a-z][a-z0-9_]{0,39}$')


@dataclass(kw_only=True)
class CustomField:
    """
    A field of the organization's own on every ticket (like OTOBO's dynamic fields), e.g. "Contract number" (text),
    "Product" (a choice) or "Warranty" (yes/no).
    """

    id: str
    tenant_id: str
    key: str
    label: str
    kind: FieldKind
    options: tuple[str, ...]
    position: int
    created_at: datetime

    def check(self) -> None:
        self.label = ' '.join(self.label.split())
        if not _KEY.match(self.key):
            raise InvalidFieldError('key')
        if not 1 <= len(self.label) <= 80:
            raise InvalidFieldError('label')
        if self.kind not in FIELD_KINDS:
            raise InvalidFieldError('kind')
        options = tuple(dict.fromkeys(' '.join(option.split()) for option in self.options if option.strip()))
        if self.kind == 'select' and not 1 <= len(options) <= OPTIONS_MAX:
            raise InvalidFieldError('options')
        if any(len(option) > 80 for option in options):
            raise InvalidFieldError('options')
        self.options = options if self.kind == 'select' else ()

    def value(self, raw: object) -> FieldValue | None:
        """The value to store; None clears it. Raises InvalidFieldError for one that does not fit."""
        if raw is None or raw == '':
            return None
        match self.kind:
            case 'checkbox':
                if not isinstance(raw, bool):
                    raise InvalidFieldError(self.key)
                return raw
            case 'number':
                if isinstance(raw, bool) or not isinstance(raw, int | float):
                    raise InvalidFieldError(self.key)
                return float(raw)
            case 'date':
                try:
                    return date.fromisoformat(str(raw)).isoformat()
                except ValueError:
                    raise InvalidFieldError(self.key) from None
            case 'select':
                if raw not in self.options:
                    raise InvalidFieldError(self.key)
                return str(raw)
            case _:
                text = str(raw).strip()
                if len(text) > 500:
                    raise InvalidFieldError(self.key)
                return text or None


@dataclass(kw_only=True)
class ChecklistItem:
    """One thing to do in a ticket (like Zammad's checklists)."""

    id: str
    tenant_id: str
    ticket_id: str
    text: str
    done: bool
    position: int
    created_at: datetime

    def check(self) -> None:
        self.text = ' '.join(self.text.split())
        if not 1 <= len(self.text) <= 300:
            raise InvalidFieldError('text')
