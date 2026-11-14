from collections.abc import Sequence
from dataclasses import dataclass

from zendilohub.core.bus.message import Command, Query
from zendilohub.core.domain.app_domain_error import ValidationError
from zendilohub.core.domain.clock import Clock
from zendilohub.core.domain.id_generator import IdGenerator
from zendilohub.core.domain.mailer import Mailer, MailMessage

from ...domain.models.notification import (
    FOLLOW_MODES,
    FOLLOWED_MAX,
    FollowedQueue,
    FollowMode,
    Notification,
    NotificationKind,
    Settings,
)
from ...domain.ports.repositories import Directory, NotificationRepository

SUBJECTS: dict[NotificationKind, str] = {
    'assigned': 'assigned to you',
    'mentioned': 'you were mentioned',
    'message': 'new message',
    'sla_breached': 'service level missed',
    'created': 'new ticket',
    'moved': 'moved to a queue you follow',
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


class InvalidFollowedQueuesError(ValidationError):
    def __init__(self) -> None:
        super().__init__('invalid_followed_queues', 'You can only follow queues whose tickets you may see')


@dataclass(frozen=True, kw_only=True)
class GetFollowedQueues(Query[Sequence[FollowedQueue]]):
    tenant_id: str
    user_id: str


class GetFollowedQueuesHandler:
    def __init__(self, notifications: NotificationRepository) -> None:
        self._notifications = notifications

    async def handle(self, query: GetFollowedQueues) -> Sequence[FollowedQueue]:
        return await self._notifications.followed(query.tenant_id, query.user_id)


@dataclass(frozen=True, kw_only=True)
class FollowQueues(Command[Sequence[FollowedQueue]]):
    """Replaces the queues the member follows; only queues whose tickets they may see."""

    tenant_id: str
    user_id: str
    queues: Sequence[FollowedQueue]


class FollowQueuesHandler:
    def __init__(self, notifications: NotificationRepository, directory: Directory) -> None:
        self._notifications = notifications
        self._directory = directory

    async def handle(self, command: FollowQueues) -> Sequence[FollowedQueue]:
        queues = list({each.queue_id: each for each in command.queues}.values())
        if len(queues) > FOLLOWED_MAX or any(each.mode not in FOLLOW_MODES for each in queues):
            raise InvalidFollowedQueuesError()
        for each in queues:
            if not await self._directory.viewers(command.tenant_id, each.queue_id, [command.user_id]):
                raise InvalidFollowedQueuesError()
        await self._notifications.follow(command.tenant_id, command.user_id, queues)
        return await self._notifications.followed(command.tenant_id, command.user_id)


@dataclass(frozen=True, kw_only=True)
class FollowersOf(Query[list[str]]):
    """Who follows the queue in one of these modes and may still see its tickets."""

    tenant_id: str
    queue_id: str
    modes: tuple[FollowMode, ...] = FOLLOW_MODES


class FollowersOfHandler:
    def __init__(self, notifications: NotificationRepository, directory: Directory) -> None:
        self._notifications = notifications
        self._directory = directory

    async def handle(self, query: FollowersOf) -> list[str]:
        followers = list(await self._notifications.followers(query.tenant_id, query.queue_id, query.modes))
        # Rights change; a follower who lost the queue hears nothing more of it.
        viewers = await self._directory.viewers(query.tenant_id, query.queue_id, followers)
        return [each for each in followers if each in viewers]


@dataclass(frozen=True)
class ForgetQueue(Command[None]):
    tenant_id: str
    queue_id: str


class ForgetQueueHandler:
    def __init__(self, notifications: NotificationRepository) -> None:
        self._notifications = notifications

    async def handle(self, command: ForgetQueue) -> None:
        await self._notifications.forget_queue(command.tenant_id, command.queue_id)
