import json
import secrets
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from zendilohub.core.bus.message import Command, Query
from zendilohub.core.domain.cipher import Cipher
from zendilohub.core.domain.clock import Clock
from zendilohub.core.domain.http_fetch import FetchBlockedError, FetchFailedError, PublicFetcher
from zendilohub.core.domain.id_generator import IdGenerator
from zendilohub.core.domain.jobs import JobQueue

from ...domain.models.chat import chat_body
from ...domain.models.webhook import (
    SIGNATURE_HEADER,
    WEBHOOKS_MAX,
    Delivery,
    InvalidWebhookError,
    Webhook,
    WebhookEvent,
    WebhookFormat,
    WebhookNotFoundError,
    signature,
)
from ...domain.ports.repositories import Tickets, WebhookRepository

DELIVER_TASK = 'integrations.deliver'
RETRIES = (60, 300, 1800)
"""Seconds before the 2nd, 3rd and 4th try."""


def _context(webhook_id: str) -> str:
    return f'integrations.webhook.{webhook_id}'


@dataclass(frozen=True)
class CreatedWebhook:
    webhook: Webhook
    secret: str
    """Shown this once."""


@dataclass(frozen=True, kw_only=True)
class SaveWebhook(Command[CreatedWebhook]):
    tenant_id: str
    name: str
    url: str
    events: tuple[WebhookEvent, ...]
    active: bool = True
    format: WebhookFormat = 'json'
    queue_ids: tuple[str, ...] = ()
    webhook_id: str | None = None
    new_secret: bool = False


class SaveWebhookHandler:
    def __init__(
        self, webhooks: WebhookRepository, tickets: Tickets, cipher: Cipher, ids: IdGenerator, clock: Clock
    ) -> None:
        self._webhooks = webhooks
        self._tickets = tickets
        self._cipher = cipher
        self._ids = ids
        self._clock = clock

    async def handle(self, command: SaveWebhook) -> CreatedWebhook:
        existing = list(await self._webhooks.of_tenant(command.tenant_id))
        found = next((each for each in existing if each.id == command.webhook_id), None)
        if command.webhook_id is not None and found is None:
            raise WebhookNotFoundError()
        if found is None and len(existing) >= WEBHOOKS_MAX:
            raise InvalidWebhookError('limit')
        webhook = found or Webhook(
            id=self._ids.new_id(),
            tenant_id=command.tenant_id,
            name='',
            url='',
            events=(),
            active=True,
            created_at=self._clock.now(),
        )
        webhook.name, webhook.url, webhook.events, webhook.active = (
            command.name,
            command.url,
            command.events,
            command.active,
        )
        webhook.format, webhook.queue_ids = command.format, command.queue_ids
        webhook.check()
        for queue_id in webhook.queue_ids:
            if await self._tickets.queue_name(command.tenant_id, queue_id) is None:
                raise InvalidWebhookError('queue_ids')
        await self._webhooks.save(webhook)
        secret = ''
        if found is None or command.new_secret:
            secret = 'whsec_' + secrets.token_urlsafe(24)
            await self._webhooks.set_secret(webhook.id, self._cipher.seal(secret, context=_context(webhook.id)))
        return CreatedWebhook(webhook, secret)


@dataclass(frozen=True, kw_only=True)
class DeleteWebhook(Command[Webhook]):
    tenant_id: str
    webhook_id: str


class DeleteWebhookHandler:
    def __init__(self, webhooks: WebhookRepository) -> None:
        self._webhooks = webhooks

    async def handle(self, command: DeleteWebhook) -> Webhook:
        found = await self._webhooks.find(command.tenant_id, command.webhook_id)
        if found is None:
            raise WebhookNotFoundError()
        await self._webhooks.delete(command.tenant_id, found.id)
        return found


@dataclass(frozen=True, kw_only=True)
class Announce(Command[int]):
    """Something happened: every active webhook that wants the event gets it (in the background)."""

    tenant_id: str
    event: WebhookEvent
    ticket_id: str | None = None
    data: dict[str, Any] | None = None
    webhook_id: str | None = None
    """Only to this one (the test button), even if it does not want the event."""


class AnnounceHandler:
    def __init__(
        self,
        webhooks: WebhookRepository,
        tickets: Tickets,
        jobs: JobQueue,
        ids: IdGenerator,
        clock: Clock,
        link_base: str = '',
    ) -> None:
        self._webhooks = webhooks
        self._tickets = tickets
        self._jobs = jobs
        self._ids = ids
        self._clock = clock
        self._link_base = link_base.rstrip('/')

    async def handle(self, command: Announce) -> int:
        webhooks = list(await self._webhooks.of_tenant(command.tenant_id))
        if command.webhook_id is None and not any(each.active and command.event in each.events for each in webhooks):
            return 0
        data: dict[str, Any] = dict(command.data or {})
        queue_id: str | None = None
        if command.ticket_id:
            facts = await self._tickets.facts(command.tenant_id, command.ticket_id)
            if facts is None:
                return 0
            queue_id = facts.queue_id
            data['ticket'] = asdict(facts)
            data['queue_name'] = await self._tickets.queue_name(command.tenant_id, facts.queue_id)
            if self._link_base:
                data['ticket_url'] = f'{self._link_base}/t/{command.tenant_id}/tickets/{facts.id}'
        targets = [
            each
            for each in webhooks
            if (command.webhook_id is not None and each.id == command.webhook_id)
            or (command.webhook_id is None and each.wants(command.event, queue_id))
        ]
        if not targets:
            return 0
        payload = {
            'id': self._ids.new_id(),
            'event': command.event,
            'created_at': self._clock.now().isoformat(),
            'tenant_id': command.tenant_id,
            'data': data,
        }
        body = json.dumps(payload, default=_json, separators=(',', ':'))
        for webhook in targets:
            await self._jobs.enqueue(DELIVER_TASK, command.tenant_id, webhook.id, body, '1')
        return len(targets)


def _json(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple | set | frozenset):
        return list(value)
    raise TypeError(type(value).__name__)


@dataclass(frozen=True)
class Deliver(Command[int | None]):
    """POSTs one event to one webhook; tries again later on failure (a worker task)."""

    tenant_id: str
    webhook_id: str
    body: str
    attempt: int = 1


class DeliverHandler:
    def __init__(
        self,
        webhooks: WebhookRepository,
        cipher: Cipher,
        fetcher: PublicFetcher,
        jobs: JobQueue,
        ids: IdGenerator,
        clock: Clock,
    ) -> None:
        self._webhooks = webhooks
        self._cipher = cipher
        self._fetcher = fetcher
        self._jobs = jobs
        self._ids = ids
        self._clock = clock

    async def handle(self, command: Deliver) -> int | None:
        webhook = await self._webhooks.find(command.tenant_id, command.webhook_id)
        sealed = await self._webhooks.secret(command.webhook_id) if webhook else None
        if webhook is None or sealed is None:
            return None
        secret = self._cipher.open(sealed, context=_context(webhook.id)) or ''
        payload = json.loads(command.body)
        event = payload.get('event', '')
        # Chat formats take their shape when they go out, so a changed format applies to retries too.
        chat = chat_body(webhook.format, payload)
        body = command.body.encode() if chat is None else json.dumps(chat, separators=(',', ':')).encode()
        status: int | None = None
        error: str | None = None
        try:
            result = await self._fetcher.fetch(
                'POST',
                webhook.url,
                content=body,
                headers={
                    'Content-Type': 'application/json',
                    'User-Agent': 'zendiloHUB-Webhooks',
                    SIGNATURE_HEADER: signature(secret, body),
                    'X-Zendilohub-Event': event,
                },
                time_limit=10,
                size_limit=64 * 1024,
            )
            status = result.status
            if not 200 <= status < 300:
                error = f'HTTP {status}'
        except FetchBlockedError:
            error = 'The address is not on the public internet'
        except FetchFailedError as failed:
            error = str(failed) or 'The address did not answer'
        now = self._clock.now()
        await self._webhooks.add_delivery(
            Delivery(
                id=self._ids.new_id(),
                webhook_id=webhook.id,
                tenant_id=webhook.tenant_id,
                event=event,
                attempt=command.attempt,
                status=status,
                error=error,
                created_at=now,
            )
        )
        webhook.last_delivery_at, webhook.last_status, webhook.last_error = now, status, error
        await self._webhooks.save(webhook)
        if error and command.attempt <= len(RETRIES):
            await self._jobs.enqueue(
                DELIVER_TASK,
                command.tenant_id,
                webhook.id,
                command.body,
                str(command.attempt + 1),
                delay=RETRIES[command.attempt - 1],
            )
        return status


@dataclass(frozen=True)
class ListWebhooks(Query[Sequence[Webhook]]):
    tenant_id: str


class ListWebhooksHandler:
    def __init__(self, webhooks: WebhookRepository) -> None:
        self._webhooks = webhooks

    async def handle(self, query: ListWebhooks) -> Sequence[Webhook]:
        return await self._webhooks.of_tenant(query.tenant_id)


@dataclass(frozen=True)
class ListDeliveries(Query[Sequence[Delivery]]):
    tenant_id: str
    webhook_id: str


class ListDeliveriesHandler:
    def __init__(self, webhooks: WebhookRepository) -> None:
        self._webhooks = webhooks

    async def handle(self, query: ListDeliveries) -> Sequence[Delivery]:
        if await self._webhooks.find(query.tenant_id, query.webhook_id) is None:
            raise WebhookNotFoundError()
        return await self._webhooks.deliveries(query.tenant_id, query.webhook_id)


@dataclass(frozen=True)
class ForgetTenant(Command[None]):
    tenant_id: str


class ForgetTenantHandler:
    def __init__(self, webhooks: WebhookRepository) -> None:
        self._webhooks = webhooks

    async def handle(self, command: ForgetTenant) -> None:
        await self._webhooks.forget_tenant(command.tenant_id)


@dataclass(frozen=True)
class ForgetQueue(Command[None]):
    tenant_id: str
    queue_id: str


class ForgetQueueHandler:
    def __init__(self, webhooks: WebhookRepository) -> None:
        self._webhooks = webhooks

    async def handle(self, command: ForgetQueue) -> None:
        await self._webhooks.forget_queue(command.tenant_id, command.queue_id)
