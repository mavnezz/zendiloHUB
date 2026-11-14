import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, get_args
from urllib.parse import urlsplit

from zendilohub.core.domain.app_domain_error import NotFoundError, ValidationError

type WebhookEvent = Literal['ticket.created', 'ticket.changed', 'message.added', 'sla.breached']
WEBHOOK_EVENTS: tuple[WebhookEvent, ...] = get_args(WebhookEvent.__value__)
type WebhookFormat = Literal['json', 'slack', 'teams']
"""`json`: the signed event as it is; `slack`: a message for a Slack incoming webhook; `teams`: an Adaptive Card
for a Microsoft Teams workflow ("When a Teams webhook request is received")."""
WEBHOOK_FORMATS: tuple[WebhookFormat, ...] = get_args(WebhookFormat.__value__)
QUEUES_MAX = 200
WEBHOOKS_MAX = 20
SIGNATURE_HEADER = 'X-Zendilohub-Signature'


class InvalidWebhookError(ValidationError):
    def __init__(self, field: str) -> None:
        super().__init__('invalid_webhook', f'Please check the webhook ({field})', {'field': field})


class WebhookNotFoundError(NotFoundError):
    def __init__(self) -> None:
        super().__init__('webhook_not_found', 'The webhook does not exist')


@dataclass(kw_only=True)
class Webhook:
    """Another system's address that hears about tickets: each event is POSTed there as JSON, signed with a secret."""

    id: str
    tenant_id: str
    name: str
    url: str
    events: tuple[WebhookEvent, ...]
    active: bool
    created_at: datetime
    format: WebhookFormat = 'json'
    queue_ids: tuple[str, ...] = ()
    """Only tickets in these queues; empty: all queues."""
    last_delivery_at: datetime | None = None
    last_status: int | None = None
    last_error: str | None = None

    def check(self) -> None:
        self.name, self.url = ' '.join(self.name.split()), self.url.strip()
        if not 1 <= len(self.name) <= 80:
            raise InvalidWebhookError('name')
        parts = urlsplit(self.url)
        if parts.scheme not in ('https', 'http') or not parts.hostname or len(self.url) > 2000:
            raise InvalidWebhookError('url')
        if not self.events or any(event not in WEBHOOK_EVENTS for event in self.events):
            raise InvalidWebhookError('events')
        self.events = tuple(event for event in WEBHOOK_EVENTS if event in self.events)
        if self.format not in WEBHOOK_FORMATS:
            raise InvalidWebhookError('format')
        if len(self.queue_ids) > QUEUES_MAX:
            raise InvalidWebhookError('queue_ids')
        self.queue_ids = tuple(dict.fromkeys(self.queue_ids))

    def wants(self, event: WebhookEvent, queue_id: str | None) -> bool:
        """Whether an event of a ticket in this queue (None: no ticket) goes here."""
        if not self.active or event not in self.events:
            return False
        return not self.queue_ids or queue_id is None or queue_id in self.queue_ids


@dataclass(frozen=True, kw_only=True)
class Delivery:
    id: str
    webhook_id: str
    tenant_id: str
    event: str
    attempt: int
    status: int | None
    error: str | None
    created_at: datetime


def signature(secret: str, body: bytes) -> str:
    """`sha256=<hex>`: the HMAC of the body with the webhook's secret, as GitHub and Stripe do it."""
    return 'sha256=' + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
