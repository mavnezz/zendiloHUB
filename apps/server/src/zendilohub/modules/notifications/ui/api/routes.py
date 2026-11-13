from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.http.access import CurrentPerson
from zendilohub.core.http.audit import Unaudited
from zendilohub.core.http.ids import Id

from ...application.commands.notify import GetSettings, ListNotifications, MarkRead, SaveSettings
from ...domain.models.notification import Notification, NotificationKind, Settings


class NotificationResponse(BaseModel):
    id: str
    kind: NotificationKind
    ticket_id: str
    ticket_number: int
    subject: str
    actor: str
    created_at: datetime
    read_at: datetime | None

    @classmethod
    def of(cls, notification: Notification) -> NotificationResponse:
        return cls(
            id=notification.id,
            kind=notification.kind,
            ticket_id=notification.ticket_id,
            ticket_number=notification.ticket_number,
            subject=notification.subject,
            actor=notification.actor,
            created_at=notification.created_at,
            read_at=notification.read_at,
        )


class InboxResponse(BaseModel):
    items: list[NotificationResponse]
    unread: int


class ReadRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    ids: list[Id] | None = Field(default=None, max_length=500)
    """Leave out: all of them."""


class SettingsBody(BaseModel):
    model_config = ConfigDict(extra='forbid')

    email: bool
    """Also by e-mail."""


def notification_routes(bus: CommandBus) -> APIRouter:
    router = APIRouter(prefix='/tenants/{tenant_id}', tags=['notifications'])

    @router.get('/notifications')
    async def notifications(
        member: CurrentPerson,
        unread: bool = False,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> InboxResponse:
        """The caller's notifications, newest first, with how many are unread."""
        inbox = await bus.query(
            ListNotifications(tenant_id=member.tenant_id, user_id=member.user_id, unread=unread, limit=limit)
        )
        return InboxResponse(items=[NotificationResponse.of(each) for each in inbox.items], unread=inbox.unread)

    @router.post('/notifications/read', dependencies=[Unaudited])
    async def read(body: ReadRequest, member: CurrentPerson) -> InboxResponse:
        await bus.execute(MarkRead(tenant_id=member.tenant_id, user_id=member.user_id, ids=body.ids))
        inbox = await bus.query(ListNotifications(tenant_id=member.tenant_id, user_id=member.user_id))
        return InboxResponse(items=[NotificationResponse.of(each) for each in inbox.items], unread=inbox.unread)

    @router.get('/me/notification-settings')
    async def settings(member: CurrentPerson) -> SettingsBody:
        found = await bus.query(GetSettings(tenant_id=member.tenant_id, user_id=member.user_id))
        return SettingsBody(email=found.email)

    @router.put('/me/notification-settings', dependencies=[Unaudited])
    async def save_settings(body: SettingsBody, member: CurrentPerson) -> SettingsBody:
        saved = await bus.execute(
            SaveSettings(Settings(tenant_id=member.tenant_id, user_id=member.user_id, email=body.email))
        )
        return SettingsBody(email=saved.email)

    return router
