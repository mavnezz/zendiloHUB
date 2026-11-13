import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from ..exceptions import InvalidTemplateError

type TemplateKind = Literal['signature', 'salutation']
NAME_MAX = 80
BODY_MAX = 10_000

PLACEHOLDERS: tuple[str, ...] = (
    'agent.name',
    'agent.title',
    'agent.email',
    'agent.signature',
    'customer.name',
    'customer.email',
    'queue.name',
    'ticket.number',
    'ticket.subject',
    'organization.name',
)
"""What signatures, salutations and auto replies may contain as `{{…}}`; anything else is refused when saved."""

_PLACEHOLDER = re.compile(r'\{\{\s*([^{}]*?)\s*\}\}')


def check_placeholders(text: str, field: str) -> None:
    for name in _PLACEHOLDER.findall(text):
        if name not in PLACEHOLDERS:
            raise InvalidTemplateError(field, name)


def render(text: str, values: Mapping[str, str]) -> str:
    """Fills the placeholders; unknown or empty values become empty text, and lines left empty by them go."""
    lines = []
    for line in text.splitlines():
        filled = _PLACEHOLDER.sub(lambda match: values.get(match.group(1), ''), line)
        if filled.strip() or not _PLACEHOLDER.search(line):
            lines.append(filled.rstrip())
    return '\n'.join(lines).strip('\n')


@dataclass(kw_only=True)
class TextTemplate:
    """A signature ("Best regards, {{agent.name}} …") or salutation ("Hello {{customer.name}},") of queues."""

    id: str
    tenant_id: str
    kind: TemplateKind
    name: str
    body: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls, *, id: str, tenant_id: str, kind: TemplateKind, name: str, body: str, now: datetime
    ) -> TextTemplate:
        template = cls(id=id, tenant_id=tenant_id, kind=kind, name='', body='', created_at=now, updated_at=now)
        template.change(name=name, body=body, now=now)
        return template

    def change(self, *, name: str, body: str, now: datetime) -> None:
        name, body = ' '.join(name.split()), body.strip('\n').rstrip()
        if not 1 <= len(name) <= NAME_MAX:
            raise InvalidTemplateError('name')
        if not body.strip() or len(body) > BODY_MAX:
            raise InvalidTemplateError('body')
        check_placeholders(body, 'body')
        self.name, self.body, self.updated_at = name, body, now


@dataclass(kw_only=True)
class PersonalSettings:
    """What a member adds to the queue's signature: their name, title and personal lines (`{{agent.signature}}`)."""

    tenant_id: str
    user_id: str
    name: str
    title: str
    signature: str

    def change(self, *, name: str, title: str, signature: str) -> None:
        name, title, signature = ' '.join(name.split()), ' '.join(title.split()), signature.strip('\n').rstrip()
        if len(name) > NAME_MAX:
            raise InvalidTemplateError('name')
        if len(title) > NAME_MAX:
            raise InvalidTemplateError('title')
        if len(signature) > BODY_MAX:
            raise InvalidTemplateError('signature')
        if '{{' in signature:
            raise InvalidTemplateError('signature')
        self.name, self.title, self.signature = name, title, signature


@dataclass(kw_only=True)
class QueueChannel:
    """How a queue writes: from which account, with which salutation and signature, and its auto reply."""

    tenant_id: str
    queue_id: str
    account_id: str | None = None
    signature_id: str | None = None
    salutation_id: str | None = None
    auto_reply: bool = False
    auto_reply_subject: str = ''
    auto_reply_body: str = ''

    def check(self) -> None:
        if len(self.auto_reply_subject) > 250:
            raise InvalidTemplateError('auto_reply_subject')
        if len(self.auto_reply_body) > BODY_MAX:
            raise InvalidTemplateError('auto_reply_body')
        if self.auto_reply and not (self.auto_reply_subject.strip() and self.auto_reply_body.strip()):
            raise InvalidTemplateError('auto_reply_body')
        check_placeholders(self.auto_reply_subject, 'auto_reply_subject')
        check_placeholders(self.auto_reply_body, 'auto_reply_body')
