import re
from dataclasses import dataclass
from datetime import datetime

from zendilohub.core.domain.app_domain_error import ConflictError, NotFoundError, ValidationError

MODULES_MAX = 500
_KEYWORD = re.compile(r'^[a-z0-9][a-z0-9_-]{0,29}$')


class InvalidTextModuleError(ValidationError):
    def __init__(self, field: str) -> None:
        super().__init__('invalid_text_module', f'Please check the text module ({field})', {'field': field})


class TextModuleNotFoundError(NotFoundError):
    def __init__(self) -> None:
        super().__init__('text_module_not_found', 'The text module does not exist')


class KeywordTakenError(ConflictError):
    def __init__(self) -> None:
        super().__init__('keyword_taken', 'Another text module has this keyword')


@dataclass(kw_only=True)
class TextModule:
    """
    A text agents insert while writing, by typing `::keyword` (like Zammad's text modules), e.g. ::thanks. Limited to
    some queues, it shows only there (like OTOBO's response templates per queue).
    """

    id: str
    tenant_id: str
    name: str
    keyword: str
    body: str
    queue_ids: tuple[str, ...]
    created_at: datetime
    updated_at: datetime

    def check(self) -> None:
        self.name, self.keyword = ' '.join(self.name.split()), self.keyword.strip().lower()
        self.body = self.body.strip('\n').rstrip()
        if not 1 <= len(self.name) <= 80:
            raise InvalidTextModuleError('name')
        if not _KEYWORD.match(self.keyword):
            raise InvalidTextModuleError('keyword')
        if not self.body.strip() or len(self.body) > 20_000:
            raise InvalidTextModuleError('body')
        self.queue_ids = tuple(dict.fromkeys(self.queue_ids))

    def fits(self, queue_id: str | None) -> bool:
        return not self.queue_ids or queue_id is None or queue_id in self.queue_ids
