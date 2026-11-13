from collections.abc import Sequence
from dataclasses import dataclass

from zendilohub.core.bus.message import Command, Query
from zendilohub.core.domain.clock import Clock
from zendilohub.core.domain.id_generator import IdGenerator
from zendilohub.core.domain.mailer import Mailer, MailMessage

from ...domain.models.notification import Notification, NotificationKind, Settings
from ...domain.ports.repositories import Directory, NotificationRepository

SUBJECTS: dict[NotificationKind, str] = {
    'assigned': 'assigned to you',
    'mentioned': 'you were mentioned',
    'message': 'new message',
    'sla_breached': 'service level missed',
}


@dataclass(frozen=True, kw_only=True)
class Notify(Command[int]):
    """Tells these members about something in a ticket (never the one who did it); returns how many were told."""

    tenant_id: str
    ticket_id: str
    kind: NotificationKind
    user_ids: Sequence[str]
    actor_id: str | None = None
    actor: str | None = None


class NotifyHandler:
    def __init__(
        self,
        notifications: NotificationRepository,
        directory: Directory,
        mailer: Mailer,
        ids: IdGenerator,
        clock: Clock,
        link_base: str,
    ) -> None:
        self._notifications = notifications
        self._directory = directory
        self._mailer = mailer
        self._ids = ids
        self._clock = clock
        self._link_base = link_base

    async def handle(self, command: Notify) -> int:
        recipients = [each for each in dict.fromkeys(command.user_ids) if each and each != command.actor_id]
        if not recipients:
            return 0
        facts = await self._directory.facts(command.tenant_id, command.ticket_id)
        if facts is None:
            return 0
        actor = command.actor or (
            await self._directory.email_of(command.tenant_id, command.actor_id) if command.actor_id else None
        )
        now = self._clock.now()
        notifications = [
            Notification(
                id=self._ids.new_id(),
                tenant_id=command.tenant_id,
                user_id=user_id,
                kind=command.kind,
                ticket_id=facts.id,
                ticket_number=facts.number,
                subject=facts.subject,
                actor=actor or 'zendiloHUB',
                created_at=now,
            )
            for user_id in recipients
        ]
        await self._notifications.add(notifications)
        for each in notifications:
            if not (await self._notifications.settings(command.tenant_id, each.user_id)).email:
                continue
            email = await self._directory.email_of(command.tenant_id, each.user_id)
            if email:
                await self._mailer.send(
                    MailMessage(
                        to=email,
                        subject=f'[#{each.ticket_number}] {each.subject}: {SUBJECTS[each.kind]}',
                        text=(
                            f'{each.actor}: {SUBJECTS[each.kind]}\n\n#{each.ticket_number} {each.subject}\n'
                            f'{self._link_base}/t/{each.tenant_id}/tickets/{each.ticket_id}\n'
                        ),
                    )
                )
        return len(notifications)


@dataclass(frozen=True, kw_only=True)
class Inbox:
    items: Sequence[Notification]
    unread: int


@dataclass(frozen=True, kw_only=True)
class ListNotifications(Query[Inbox]):
    tenant_id: str
    user_id: str
    unread: bool = False
    limit: int = 50


class ListNotificationsHandler:
    def __init__(self, notifications: NotificationRepository) -> None:
        self._notifications = notifications

    async def handle(self, query: ListNotifications) -> Inbox:
        return Inbox(
            items=await self._notifications.of_user(
                query.tenant_id, query.user_id, unread=query.unread, limit=query.limit
            ),
            unread=await self._notifications.unread(query.tenant_id, query.user_id),
        )


@dataclass(frozen=True, kw_only=True)
class MarkRead(Command[None]):
    tenant_id: str
    user_id: str
    ids: Sequence[str] | None = None


class MarkReadHandler:
    def __init__(self, notifications: NotificationRepository, clock: Clock) -> None:
        self._notifications = notifications
        self._clock = clock

    async def handle(self, command: MarkRead) -> None:
        await self._notifications.mark_read(command.tenant_id, command.user_id, command.ids, self._clock.now())


@dataclass(frozen=True, kw_only=True)
class GetSettings(Query[Settings]):
    tenant_id: str
    user_id: str


class GetSettingsHandler:
    def __init__(self, notifications: NotificationRepository) -> None:
        self._notifications = notifications

    async def handle(self, query: GetSettings) -> Settings:
        return await self._notifications.settings(query.tenant_id, query.user_id)


@dataclass(frozen=True)
class SaveSettings(Command[Settings]):
    settings: Settings


class SaveSettingsHandler:
    def __init__(self, notifications: NotificationRepository) -> None:
        self._notifications = notifications

    async def handle(self, command: SaveSettings) -> Settings:
        await self._notifications.save_settings(command.settings)
        return command.settings


@dataclass(frozen=True)
class Forget(Command[None]):
    tenant_id: str | None
    user_id: str | None = None
    """None: everything of the organization."""


class ForgetHandler:
    def __init__(self, notifications: NotificationRepository) -> None:
        self._notifications = notifications

    async def handle(self, command: Forget) -> None:
        if command.user_id is None:
            assert command.tenant_id is not None
            await self._notifications.forget_tenant(command.tenant_id)
        else:
            await self._notifications.forget(command.tenant_id, command.user_id)
