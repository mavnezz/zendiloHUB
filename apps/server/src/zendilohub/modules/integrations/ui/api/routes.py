from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.http.access import Member, member_with
from zendilohub.core.http.audit import Unaudited, audited, note_audit
from zendilohub.core.http.ids import Id

from ...application.commands.webhooks import Announce, DeleteWebhook, ListDeliveries, ListWebhooks, SaveWebhook
from ...domain.models.webhook import Delivery, Webhook, WebhookEvent, WebhookFormat

Admin = Annotated[Member, member_with('integrations.manage', people_only=True)]


class WebhookRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: str = Field(max_length=80)
    url: str = Field(max_length=2000)
    """Public internet only (https recommended)."""
    events: list[WebhookEvent] = Field(min_length=1)
    active: bool = True
    format: WebhookFormat = 'json'
    """`json`: the signed event; `slack`: a Slack incoming webhook; `teams`: a Microsoft Teams workflow."""
    queue_ids: list[Id] = Field(default_factory=list, max_length=200)
    """Only tickets in these queues; empty: all queues."""
    new_secret: bool = False
    """Changes only: make a new secret (the old one stops working at once)."""


class WebhookResponse(BaseModel):
    id: str
    name: str
    url: str
    events: list[WebhookEvent]
    active: bool
    format: WebhookFormat
    queue_ids: list[str]
    created_at: datetime
    last_delivery_at: datetime | None
    last_status: int | None
    last_error: str | None
    secret: str | None = None
    """Only in the answer that made it: `whsec_…`; it signs every delivery (header `X-Zendilohub-Signature`)."""

    @classmethod
    def of(cls, webhook: Webhook, secret: str | None = None) -> WebhookResponse:
        return cls(
            id=webhook.id,
            name=webhook.name,
            url=webhook.url,
            events=list(webhook.events),
            active=webhook.active,
            format=webhook.format,
            queue_ids=list(webhook.queue_ids),
            created_at=webhook.created_at,
            last_delivery_at=webhook.last_delivery_at,
            last_status=webhook.last_status,
            last_error=webhook.last_error,
            secret=secret or None,
        )


class WebhookDeliveryResponse(BaseModel):
    id: str
    event: str
    attempt: int
    status: int | None
    error: str | None
    created_at: datetime

    @classmethod
    def of(cls, delivery: Delivery) -> WebhookDeliveryResponse:
        return cls(
            id=delivery.id,
            event=delivery.event,
            attempt=delivery.attempt,
            status=delivery.status,
            error=delivery.error,
            created_at=delivery.created_at,
        )


def integration_routes(bus: CommandBus) -> APIRouter:
    router = APIRouter(prefix='/tenants/{tenant_id}', tags=['integrations'])

    @router.get('/webhooks')
    async def webhooks(member: Admin) -> list[WebhookResponse]:
        return [WebhookResponse.of(each) for each in await bus.query(ListWebhooks(member.tenant_id))]

    @router.post('/webhooks', status_code=201, dependencies=[audited('webhook.created')])
    async def create(body: WebhookRequest, request: Request, member: Admin) -> WebhookResponse:
        """Deliveries are POSTs with a JSON body, signed in `X-Zendilohub-Signature: sha256=<HMAC of the body>`."""
        created = await bus.execute(
            SaveWebhook(
                tenant_id=member.tenant_id,
                name=body.name,
                url=body.url,
                events=tuple(body.events),
                active=body.active,
                format=body.format,
                queue_ids=tuple(body.queue_ids),
            )
        )
        note_audit(request, target=created.webhook.name)
        return WebhookResponse.of(created.webhook, created.secret)

    @router.patch('/webhooks/{webhook_id}', dependencies=[audited('webhook.updated')])
    async def update(webhook_id: Id, body: WebhookRequest, request: Request, member: Admin) -> WebhookResponse:
        saved = await bus.execute(
            SaveWebhook(
                tenant_id=member.tenant_id,
                name=body.name,
                url=body.url,
                events=tuple(body.events),
                active=body.active,
                format=body.format,
                queue_ids=tuple(body.queue_ids),
                webhook_id=webhook_id,
                new_secret=body.new_secret,
            )
        )
        note_audit(request, target=saved.webhook.name)
        return WebhookResponse.of(saved.webhook, saved.secret)

    @router.delete(
        '/webhooks/{webhook_id}', status_code=204, response_class=Response, dependencies=[audited('webhook.deleted')]
    )
    async def delete(webhook_id: Id, request: Request, member: Admin) -> None:
        deleted = await bus.execute(DeleteWebhook(tenant_id=member.tenant_id, webhook_id=webhook_id))
        note_audit(request, target=deleted.name)

    @router.post('/webhooks/{webhook_id}/test', status_code=202, response_class=Response, dependencies=[Unaudited])
    async def test(webhook_id: Id, member: Admin) -> None:
        """Sends a `ping` event now (see the deliveries for the answer)."""
        await bus.query(ListDeliveries(member.tenant_id, webhook_id))
        await bus.execute(
            Announce(tenant_id=member.tenant_id, event='ticket.created', data={'ping': True}, webhook_id=webhook_id)
        )

    @router.get('/webhooks/{webhook_id}/deliveries')
    async def deliveries(webhook_id: Id, member: Admin) -> list[WebhookDeliveryResponse]:
        """The last 50 tries, newest first."""
        return [
            WebhookDeliveryResponse.of(each) for each in await bus.query(ListDeliveries(member.tenant_id, webhook_id))
        ]

    return router
